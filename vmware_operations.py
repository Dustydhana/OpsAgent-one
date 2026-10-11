"""Guarded VMware ESXi/vCenter discovery and lifecycle operations.

The module keeps control-plane mutations outside the LLM tool loop. Changes
require human approval, an environment allowlist, role checks in the caller,
and an audit record. Dry-run is the safe default and does not call a mutation
API. New-VM provisioning and host patching deliberately remain plan-only
because their safe implementation requires site-specific images, networks,
storage policy, evacuation, and rollback rules.
"""

import ssl
import time
from datetime import datetime, timezone
from uuid import uuid4

import config
import database
import ops_log

try:
    from pyVim.connect import Disconnect, SmartConnect
    from pyVmomi import vim
except ImportError:  # Keep non-VMware OpsAgent features usable without extras.
    Disconnect = SmartConnect = None
    vim = None


MUTATING_ACTIONS = {
    "power_on_vm", "power_off_vm", "reboot_guest", "create_snapshot",
    "remove_snapshot", "resize_vm", "extend_disk", "enter_maintenance",
    "exit_maintenance", "reboot_host", "shutdown_host", "create_vm", "patch_host",
}

# These actions have a bounded implementation through the vSphere API. The
# remaining actions are still useful as auditable dry-run plans in the demo.
LIVE_ACTIONS = MUTATING_ACTIONS - {"create_vm", "patch_host"}

HOST_ACTIONS = {
    "enter_maintenance", "exit_maintenance", "reboot_host", "shutdown_host", "patch_host",
}


def _safe_error(value, limit=800):
    return str(value or "").strip()[:limit]


def _wait_for_task(task, timeout=180):
    deadline = time.monotonic() + max(1, int(timeout))
    while time.monotonic() < deadline:
        state = task.info.state
        if state == vim.TaskInfo.State.success:
            return task.info.result
        if state == vim.TaskInfo.State.error:
            error = task.info.error
            raise RuntimeError(getattr(error, "msg", None) or str(error))
        time.sleep(1)
    raise TimeoutError(f"VMware task did not finish within {timeout} seconds")


class VMwareClient:
    """Small pyVmomi boundary that is easy to replace with a fake in tests."""

    def __init__(self, endpoint=None, username=None, password=None, port=None, verify_ssl=None):
        self.endpoint = str(endpoint or config.VMWARE_ENDPOINT).strip()
        self.username = str(username or config.VMWARE_USERNAME).strip()
        self.password = config.VMWARE_PASSWORD if password is None else password
        self.port = int(port or config.VMWARE_PORT)
        self.verify_ssl = config.VMWARE_VERIFY_SSL if verify_ssl is None else bool(verify_ssl)
        self.service_instance = None
        self.content = None

    def connect(self):
        if SmartConnect is None:
            raise RuntimeError("pyvmomi is not installed; run pip install -r requirements.txt")
        if not self.endpoint or not self.username or not self.password:
            raise RuntimeError("VMWARE_ENDPOINT, VMWARE_USERNAME, and VMWARE_PASSWORD are required")
        kwargs = {
            "host": self.endpoint, "user": self.username,
            "pwd": self.password, "port": self.port,
        }
        if self.verify_ssl:
            kwargs["sslContext"] = ssl.create_default_context()
        else:
            kwargs["disableSslCertValidation"] = True
        self.service_instance = SmartConnect(**kwargs)
        self.content = self.service_instance.RetrieveContent()
        return self

    def close(self):
        if self.service_instance is not None and Disconnect is not None:
            Disconnect(self.service_instance)
        self.service_instance = None
        self.content = None

    def __enter__(self):
        return self.connect()

    def __exit__(self, *_args):
        self.close()

    def _objects(self, object_type):
        view = self.content.viewManager.CreateContainerView(
            self.content.rootFolder, [object_type], True
        )
        try:
            return list(view.view)
        finally:
            view.Destroy()

    def _find_vm(self, name):
        target = str(name or "").strip().casefold()
        matches = [item for item in self._objects(vim.VirtualMachine)
                   if str(item.name).casefold() == target]
        if len(matches) != 1:
            raise ValueError(f"Expected exactly one VM named {name!r}; found {len(matches)}")
        return matches[0]

    def _host(self):
        hosts = self._objects(vim.HostSystem)
        if len(hosts) != 1:
            raise ValueError(f"Standalone operations require exactly one ESXi host; found {len(hosts)}")
        return hosts[0]

    @staticmethod
    def _snapshot(snapshot, name):
        for node in snapshot.rootSnapshotList if snapshot else []:
            if node.name == name:
                return node.snapshot
            nested = VMwareClient._snapshot_tree(node.childSnapshotList, name)
            if nested:
                return nested
        return None

    @staticmethod
    def _snapshot_tree(nodes, name):
        for node in nodes or []:
            if node.name == name:
                return node.snapshot
            nested = VMwareClient._snapshot_tree(node.childSnapshotList, name)
            if nested:
                return nested
        return None

    def describe(self):
        about = self.content.about
        hosts = []
        for host in self._objects(vim.HostSystem):
            summary = host.summary
            hardware = summary.hardware
            quick = summary.quickStats
            hosts.append({
                "name": host.name,
                "connection_state": str(summary.runtime.connectionState),
                "power_state": str(summary.runtime.powerState),
                "maintenance_mode": bool(summary.runtime.inMaintenanceMode),
                "vendor": hardware.vendor, "model": hardware.model,
                "cpu_threads": hardware.numCpuThreads,
                "cpu_mhz": hardware.cpuMhz,
                "memory_gib": round(hardware.memorySize / (1024 ** 3), 2),
                "cpu_usage_mhz": quick.overallCpuUsage,
                "memory_usage_gib": round((quick.overallMemoryUsage or 0) / 1024, 2),
            })
        datastores = []
        for datastore in self._objects(vim.Datastore):
            summary = datastore.summary
            datastores.append({
                "name": summary.name, "accessible": bool(summary.accessible),
                "type": summary.type,
                "capacity_gib": round(summary.capacity / (1024 ** 3), 2),
                "free_gib": round(summary.freeSpace / (1024 ** 3), 2),
            })
        networks = [{"name": item.name} for item in self._objects(vim.Network)]
        vms = []
        for vm in self._objects(vim.VirtualMachine):
            summary = vm.summary
            config_summary = summary.config
            guest = summary.guest
            vms.append({
                "name": vm.name, "power_state": str(summary.runtime.powerState),
                "guest_os": config_summary.guestFullName or config_summary.guestId,
                "cpu": config_summary.numCpu,
                "memory_mb": config_summary.memorySizeMB,
                "tools_status": str(guest.toolsStatus),
                "ip_address": guest.ipAddress,
                "snapshot_count": self._count_snapshots(vm.snapshot),
            })
        return {
            "endpoint": self.endpoint,
            "product": about.fullName, "version": about.version, "build": about.build,
            "api_type": about.apiType, "hosts": hosts, "datastores": datastores,
            "networks": networks, "vms": vms,
        }

    @staticmethod
    def _count_snapshots(snapshot):
        def count(nodes):
            return sum(1 + count(node.childSnapshotList) for node in (nodes or []))
        return count(snapshot.rootSnapshotList) if snapshot else 0

    def execute(self, action, target, **params):
        if action in HOST_ACTIONS:
            host = self._host()
            if action == "enter_maintenance":
                return _wait_for_task(host.EnterMaintenanceMode_Task(
                    timeout=int(params.get("timeout") or 300), evacuatePoweredOffVms=True
                ))
            if action == "exit_maintenance":
                return _wait_for_task(host.ExitMaintenanceMode_Task(timeout=300))
            if action == "reboot_host":
                if not host.runtime.inMaintenanceMode:
                    raise ValueError("ESXi must be in maintenance mode before an approved reboot")
                return _wait_for_task(host.RebootHost_Task(force=False))
            if action == "shutdown_host":
                if not host.runtime.inMaintenanceMode:
                    raise ValueError("ESXi must be in maintenance mode before an approved shutdown")
                return _wait_for_task(host.ShutdownHost_Task(force=False))
        vm = self._find_vm(target)
        if action == "power_on_vm":
            return _wait_for_task(vm.PowerOnVM_Task())
        if action == "power_off_vm":
            return _wait_for_task(vm.PowerOffVM_Task())
        if action == "reboot_guest":
            vm.RebootGuest()
            return None
        if action == "create_snapshot":
            return _wait_for_task(vm.CreateSnapshot_Task(
                name=params["snapshot_name"], description=params.get("description") or "",
                memory=False, quiesce=False,
            ))
        if action == "remove_snapshot":
            snapshot = self._snapshot(vm.snapshot, params["snapshot_name"])
            if not snapshot:
                raise ValueError(f"Snapshot {params['snapshot_name']!r} was not found on {target!r}")
            return _wait_for_task(snapshot.RemoveSnapshot_Task(removeChildren=False))
        if action in {"resize_vm", "extend_disk"}:
            if str(vm.runtime.powerState) != "poweredOff":
                raise ValueError(f"{action} requires VM {target!r} to be powered off")
            spec = vim.vm.ConfigSpec()
            if action == "resize_vm":
                spec.numCPUs = int(params["cpu_count"])
                spec.memoryMB = int(params["memory_mb"])
            else:
                disks = [device for device in vm.config.hardware.device
                         if isinstance(device, vim.vm.device.VirtualDisk)]
                if len(disks) != 1:
                    raise ValueError("Disk extension requires a VM with exactly one virtual disk")
                disk = disks[0]
                requested_kb = int(params["disk_gib"]) * 1024 * 1024
                if requested_kb <= disk.capacityInKB:
                    raise ValueError("New disk size must be larger than the current virtual disk")
                disk.capacityInKB = requested_kb
                change = vim.vm.device.VirtualDeviceSpec()
                change.operation = vim.vm.device.VirtualDeviceSpec.Operation.edit
                change.device = disk
                spec.deviceChange = [change]
            return _wait_for_task(vm.ReconfigVM_Task(spec=spec))
        raise RuntimeError(f"Live VMware action {action!r} is not implemented")


def describe_environment(client=None):
    if client is not None:
        return client.describe()
    with VMwareClient() as session:
        return session.describe()


def sync_inventory(environment):
    """Persist a relational snapshot of VMware discovery in PostgreSQL."""
    endpoint = str(environment.get("endpoint") or config.VMWARE_ENDPOINT).strip()
    if not endpoint:
        raise ValueError("VMware inventory requires an endpoint")
    database.initialize()
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""INSERT INTO ops_agent.vmware_endpoints
                (endpoint,product,version,build,api_type,last_seen_at)
                VALUES (%s,%s,%s,%s,%s,NOW())
                ON CONFLICT (endpoint) DO UPDATE SET product=EXCLUDED.product,
                version=EXCLUDED.version,build=EXCLUDED.build,api_type=EXCLUDED.api_type,
                last_seen_at=NOW()""", (
                    endpoint, environment.get("product") or "Unknown VMware endpoint",
                    environment.get("version"), environment.get("build"),
                    environment.get("api_type"),
                ))
            # Each refresh is a complete endpoint snapshot. Replacing child
            # rows prevents deleted VMs, networks, or datastores from lingering.
            for table in (
                "vmware_hosts", "vmware_datastores", "vmware_networks",
                "vmware_virtual_machines",
            ):
                cursor.execute(f"DELETE FROM ops_agent.{table} WHERE endpoint=%s", (endpoint,))
            for row in environment.get("hosts") or []:
                cursor.execute("""INSERT INTO ops_agent.vmware_hosts
                    (endpoint,host_name,connection_state,power_state,maintenance_mode,vendor,
                     model,cpu_threads,memory_gib,cpu_usage_mhz,memory_usage_gib,last_seen_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
                    ON CONFLICT (endpoint,host_name) DO UPDATE SET
                    connection_state=EXCLUDED.connection_state,power_state=EXCLUDED.power_state,
                    maintenance_mode=EXCLUDED.maintenance_mode,vendor=EXCLUDED.vendor,
                    model=EXCLUDED.model,cpu_threads=EXCLUDED.cpu_threads,
                    memory_gib=EXCLUDED.memory_gib,cpu_usage_mhz=EXCLUDED.cpu_usage_mhz,
                    memory_usage_gib=EXCLUDED.memory_usage_gib,last_seen_at=NOW()""", (
                        endpoint, row.get("name"), row.get("connection_state"), row.get("power_state"),
                        bool(row.get("maintenance_mode")), row.get("vendor"), row.get("model"),
                        row.get("cpu_threads"), row.get("memory_gib"), row.get("cpu_usage_mhz"),
                        row.get("memory_usage_gib"),
                    ))
            for row in environment.get("datastores") or []:
                cursor.execute("""INSERT INTO ops_agent.vmware_datastores
                    (endpoint,datastore_name,accessible,datastore_type,capacity_gib,free_gib,last_seen_at)
                    VALUES (%s,%s,%s,%s,%s,%s,NOW())
                    ON CONFLICT (endpoint,datastore_name) DO UPDATE SET
                    accessible=EXCLUDED.accessible,datastore_type=EXCLUDED.datastore_type,
                    capacity_gib=EXCLUDED.capacity_gib,free_gib=EXCLUDED.free_gib,last_seen_at=NOW()""", (
                        endpoint, row.get("name"), row.get("accessible"), row.get("type"),
                        row.get("capacity_gib"), row.get("free_gib"),
                    ))
            for row in environment.get("networks") or []:
                cursor.execute("""INSERT INTO ops_agent.vmware_networks
                    (endpoint,network_name,last_seen_at) VALUES (%s,%s,NOW())
                    ON CONFLICT (endpoint,network_name) DO UPDATE SET last_seen_at=NOW()""",
                    (endpoint, row.get("name")))
            for row in environment.get("vms") or []:
                cursor.execute("""INSERT INTO ops_agent.vmware_virtual_machines
                    (endpoint,vm_name,power_state,guest_os,cpu_count,memory_mb,tools_status,
                     ip_address,snapshot_count,last_seen_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
                    ON CONFLICT (endpoint,vm_name) DO UPDATE SET power_state=EXCLUDED.power_state,
                    guest_os=EXCLUDED.guest_os,cpu_count=EXCLUDED.cpu_count,
                    memory_mb=EXCLUDED.memory_mb,tools_status=EXCLUDED.tools_status,
                    ip_address=EXCLUDED.ip_address,snapshot_count=EXCLUDED.snapshot_count,
                    last_seen_at=NOW()""", (
                        endpoint, row.get("name"), row.get("power_state"), row.get("guest_os"),
                        row.get("cpu"), row.get("memory_mb"), row.get("tools_status"),
                        row.get("ip_address"), row.get("snapshot_count"),
                    ))
        connection.commit()
    return {
        "endpoint": endpoint, "hosts": len(environment.get("hosts") or []),
        "datastores": len(environment.get("datastores") or []),
        "networks": len(environment.get("networks") or []),
        "vms": len(environment.get("vms") or []),
    }


def _guard(action, approved):
    if action not in MUTATING_ACTIONS:
        raise ValueError(f"Unknown VMware action: {action}")
    if not approved:
        raise PermissionError("Explicit human approval is required")
    if action not in config.VMWARE_ALLOWED_ACTIONS:
        raise PermissionError(f"{action} is not present in VMWARE_ALLOWED_ACTIONS")


def _validate(action, target, params):
    if action not in HOST_ACTIONS and not str(target or "").strip():
        raise ValueError("An exact VM name is required")
    if action in {"create_snapshot", "remove_snapshot"}:
        name = str(params.get("snapshot_name") or "").strip()
        if not name or len(name) > 80:
            raise ValueError("A snapshot name of 1-80 characters is required")
    if action == "resize_vm":
        if not 1 <= int(params.get("cpu_count") or 0) <= 128:
            raise ValueError("CPU count must be between 1 and 128")
        if not 512 <= int(params.get("memory_mb") or 0) <= 1048576:
            raise ValueError("Memory must be between 512 and 1048576 MB")
    if action == "extend_disk" and not 1 <= int(params.get("disk_gib") or 0) <= 65536:
        raise ValueError("New disk size must be between 1 and 65536 GiB")
    if action == "create_vm":
        required = ("vm_name", "guest_id", "datastore", "network", "disk_gib", "memory_mb", "cpu_count")
        missing = [name for name in required if not params.get(name)]
        if missing:
            raise ValueError("Create-VM plan is missing: " + ", ".join(missing))
    if action == "patch_host" and not str(params.get("patch_baseline") or "").strip():
        raise ValueError("An exact approved patch baseline or offline-bundle identifier is required")


def _audit(action, target, approved, result, actor, context, started_at):
    completed_at = datetime.now(timezone.utc)
    database.initialize()
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""INSERT INTO ops_agent.cloud_operation_audit
                (provider,actor,action,target,approved,dry_run,success,instance_id,
                 snapshot_id,message,error_message,request_id,source,requester,approver,
                 started_at,completed_at,duration_ms,before_status,after_status)
                VALUES ('vmware',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    actor, action, target, bool(approved), config.VMWARE_DRY_RUN,
                    result.get("success"), result.get("vm_name"), result.get("snapshot_name"),
                    result.get("message"), _safe_error(result.get("error")),
                    context["request_id"], context["source"], context["requester"],
                    context["approver"], started_at, completed_at,
                    max(0, int((completed_at - started_at).total_seconds() * 1000)),
                    result.get("before_status"), result.get("after_status"),
                ))
        connection.commit()


def execute(action, target="host", *, approved=False, actor="unknown", client=None,
            request_id=None, source="api", requester=None, approver=None, **params):
    """Validate and optionally execute one approved, allowlisted VMware action."""
    started_at = datetime.now(timezone.utc)
    target = str(target or "").strip()
    context = {
        "request_id": str(request_id or f"VMW-{uuid4().hex[:10].upper()}"),
        "source": str(source or "api"), "requester": str(requester or actor or "unknown"),
        "approver": str(approver or actor or "") if approved else None,
    }
    result = {"action": action, "target": target, "request_id": context["request_id"],
              "dry_run": config.VMWARE_DRY_RUN, "success": False}
    try:
        _guard(action, approved)
        _validate(action, target, params)
        if config.VMWARE_DRY_RUN:
            result.update(success=True, message=(
                "Dry-run validated: no VMware change was made. "
                + ("This workflow requires a site-specific implementation before live use."
                   if action not in LIVE_ACTIONS else "Set VMWARE_DRY_RUN=false only after licensed-lab validation.")
            ))
        else:
            if action not in LIVE_ACTIONS:
                raise RuntimeError(
                    f"{action} is plan-only: implement the approved image/baseline, network, "
                    "storage, evacuation, verification, and rollback policy before live use"
                )
            if client is not None:
                client.execute(action, target, **params)
            else:
                with VMwareClient() as session:
                    session.execute(action, target, **params)
            result.update(success=True, message="VMware action completed", vm_name=(
                None if action in HOST_ACTIONS else target
            ), snapshot_name=params.get("snapshot_name"))
    except Exception as exc:
        result["error"] = _safe_error(exc)
    try:
        _audit(action, target, approved, result, actor, context, started_at)
    except Exception as exc:
        ops_log.write("vmware", "ERROR", "audit_failed", _safe_error(exc), context["request_id"])
    ops_log.write(
        "vmware", "INFO" if result["success"] else "ERROR",
        "operation_completed" if result["success"] else "operation_failed",
        f"action={action}; target={target}; dry_run={config.VMWARE_DRY_RUN}; "
        f"error={result.get('error', '')}", context["request_id"],
    )
    return result


def audit_summary(hours=24, organization_id=None):
    organization_id = str(organization_id or config.DEFAULT_ORGANIZATION_ID or "").strip()
    database.initialize()
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""SELECT COUNT(*),
                COUNT(*) FILTER (WHERE success IS TRUE),
                COUNT(*) FILTER (WHERE success IS FALSE),
                COUNT(*) FILTER (WHERE success IS NULL)
                FROM ops_agent.cloud_operation_audit
                WHERE organization_id=%s AND provider='vmware' AND occurred_at >= NOW() - (%s * INTERVAL '1 hour')""",
                (organization_id,max(1, int(hours))))
            total, succeeded, failed, unknown = cursor.fetchone()
    return {"total": total, "succeeded": succeeded, "failed": failed, "unknown": unknown}


def audit_recent(hours=24, limit=100, organization_id=None):
    organization_id = str(organization_id or config.DEFAULT_ORGANIZATION_ID or "").strip()
    database.initialize()
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""SELECT occurred_at,request_id,source,requester,approver,actor,
                action,target,approved,dry_run,success,duration_ms,error_message
                FROM ops_agent.cloud_operation_audit
                WHERE organization_id=%s AND provider='vmware' AND occurred_at >= NOW() - (%s * INTERVAL '1 hour')
                ORDER BY occurred_at DESC LIMIT %s""",
                (organization_id,max(1, int(hours)), max(1, min(int(limit), 1000))))
            rows = cursor.fetchall()
    return [{
        "Time": row[0].astimezone().strftime("%Y-%m-%d %H:%M:%S"),
        "Request ID": row[1] or "", "Source": row[2], "Requester": row[3],
        "Approver": row[4] or "", "Actor": row[5], "Action": row[6],
        "Target": row[7], "Approved": row[8], "Mode": "Dry run" if row[9] else "Live",
        "Status": "Succeeded" if row[10] is True else "Failed" if row[10] is False else "Unknown",
        "Duration ms": row[11], "Error": row[12] or "",
    } for row in rows]

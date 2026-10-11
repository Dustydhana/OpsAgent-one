"""Guarded SCCM/MECM software-update deployment facade.

Simulation mode is intentionally the default so the workflow can be demonstrated
without a Configuration Manager installation.  A live AdminService/PowerShell
backend can implement the same small client interface later.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from threading import Lock
from uuid import uuid4
import base64
import json
import time

import config
import ops_log
from aws_operations import _session


PATCH_BATCHES = {
    "test-day-1", "test-day-2",
    "infra-day-1", "infra-day-2",
    "prod-day-1", "prod-day-2", "prod-day-3", "prod-day-4",
}


@dataclass
class Deployment:
    deployment_id: str
    name: str
    collection: str
    software_update_group: str
    batch: str
    available_at: str
    deadline_at: str
    allow_reboot: bool
    status: str = "scheduled"
    compliant: int = 0
    in_progress: int = 0
    failed: int = 0
    pending_reboot: int = 0


class SimulatedSCCMClient:
    """In-memory SCCM substitute for demos and automated tests."""

    def __init__(self):
        self._deployments = {}
        self._lock = Lock()

    def list_collections(self):
        return list(config.SCCM_SIMULATED_COLLECTIONS)

    def create_deployment(self, deployment):
        with self._lock:
            self._deployments[deployment.deployment_id] = deployment
        return asdict(deployment)

    def get_deployment(self, deployment_id):
        deployment = self._deployments.get(deployment_id)
        return asdict(deployment) if deployment else None

    def set_compliance(self, deployment_id, **counts):
        """Test hook that represents compliance data returned by SCCM."""
        with self._lock:
            deployment = self._deployments.get(deployment_id)
            if not deployment:
                return None
            for field in ("compliant", "in_progress", "failed", "pending_reboot"):
                if field in counts:
                    setattr(deployment, field, max(0, int(counts[field])))
            if deployment.failed:
                deployment.status = "attention_required"
            elif deployment.in_progress:
                deployment.status = "in_progress"
            elif deployment.pending_reboot:
                deployment.status = "patched_reboot_deferred"
            elif deployment.compliant:
                deployment.status = "complete"
            return asdict(deployment)


_SIMULATOR = SimulatedSCCMClient()
_LIVE_CACHE = {"loaded_at": 0.0, "data": None}
_LIVE_LOCK = Lock()


class SsmSCCMClient:
    """Read SCCM through a fixed SSM document executed on the site server."""

    def _collect(self):
        if not config.SCCM_INSTANCE_ID:
            raise RuntimeError("SCCM_INSTANCE_ID is not configured")
        client = _session().client("ssm", region_name=config.SCCM_REGION)
        request_id = f"SCCM-{uuid4().hex[:10].upper()}"
        ops_log.write("sccm", "INFO", "inventory_requested", json.dumps({
            "requester": "opsagent-sccm-connector", "target": config.SCCM_INSTANCE_ID,
            "document": config.SCCM_INVENTORY_DOCUMENT, "status": "requested",
        }), request_id)
        response = client.send_command(
            InstanceIds=[config.SCCM_INSTANCE_ID],
            DocumentName=config.SCCM_INVENTORY_DOCUMENT,
            TimeoutSeconds=config.SCCM_COMMAND_TIMEOUT_SECONDS,
            Comment=f"OpsAgent SCCM inventory {request_id}",
        )
        command_id = response["Command"]["CommandId"]
        deadline = time.monotonic() + config.SCCM_COMMAND_TIMEOUT_SECONDS
        invocation = None
        while time.monotonic() < deadline:
            try:
                invocation = client.get_command_invocation(
                    CommandId=command_id, InstanceId=config.SCCM_INSTANCE_ID
                )
            except client.exceptions.InvocationDoesNotExist:
                time.sleep(2)
                continue
            if invocation.get("Status") in {"Success", "Cancelled", "TimedOut", "Failed", "Cancelling"}:
                break
            time.sleep(2)
        status = (invocation or {}).get("Status", "TimedOut")
        stdout = str((invocation or {}).get("StandardOutputContent") or "")
        stderr = str((invocation or {}).get("StandardErrorContent") or "")
        if status != "Success":
            ops_log.write("sccm", "ERROR", "inventory_failed", json.dumps({
                "target": config.SCCM_INSTANCE_ID, "command_id": command_id,
                "status": status, "error": stderr[-4000:],
            }), request_id)
            raise RuntimeError(stderr.strip() or f"SCCM inventory command ended with {status}")
        marker = "OPSAGENT_JSON_BASE64:"
        line = next((part.strip() for part in stdout.splitlines() if part.strip().startswith(marker)), "")
        if not line:
            raise RuntimeError("SCCM runbook returned no structured inventory payload")
        data = json.loads(base64.b64decode(line[len(marker):]).decode("utf-8"))
        data.update({"mode": "ssm", "instance_id": config.SCCM_INSTANCE_ID, "command_id": command_id})
        ops_log.write("sccm", "INFO", "inventory_completed", json.dumps({
            "target": config.SCCM_INSTANCE_ID, "command_id": command_id,
            "status": "success", "summary": data.get("summary", {}),
        }), request_id)
        return data

    def inventory(self, force=False):
        with _LIVE_LOCK:
            fresh = time.monotonic() - _LIVE_CACHE["loaded_at"] < config.SCCM_CACHE_SECONDS
            if _LIVE_CACHE["data"] is not None and fresh and not force:
                return _LIVE_CACHE["data"]
            data = self._collect()
            _LIVE_CACHE.update({"loaded_at": time.monotonic(), "data": data})
            return data

    def list_collections(self):
        return [row.get("Name") for row in self.inventory().get("collections", []) if row.get("Name")]


_SSM_CLIENT = SsmSCCMClient()


def _client(client=None):
    if client:
        return client
    if config.SCCM_MODE == "simulation":
        return _SIMULATOR
    if config.SCCM_MODE == "ssm":
        return _SSM_CLIENT
    raise RuntimeError("SCCM_MODE must be 'simulation' or 'ssm'")


def status():
    return {
        "mode": config.SCCM_MODE,
        "configured": bool(config.SCCM_INSTANCE_ID) if config.SCCM_MODE == "ssm" else True,
        "instance_id": config.SCCM_INSTANCE_ID or None,
        "region": config.SCCM_REGION,
        "document": config.SCCM_INVENTORY_DOCUMENT,
    }


def inventory(force=False, client=None):
    selected = _client(client)
    if hasattr(selected, "inventory"):
        return {"success": True, **selected.inventory(force=force)}
    collections = selected.list_collections()
    return {"success": True, "mode": "simulation", "summary": {
        "devices": 0, "active_clients": 0, "collections": len(collections),
        "deployments": 0, "update_groups": 0,
    }, "devices": [], "collections": [{"Name": name} for name in collections],
        "deployments": [], "update_groups": []}


def list_collections(client=None):
    return {"success": True, "mode": config.SCCM_MODE, "collections": _client(client).list_collections()}


def create_patch_deployment(
    *, name, collection, software_update_group, batch, available_at,
    deadline_at, allow_reboot=False, approved=False, client=None,
):
    """Create a guarded deployment using an approved collection and patch batch."""
    if "create_patch_deployment" not in config.SCCM_ALLOWED_ACTIONS:
        return {"success": False, "error": "Action is disabled by SCCM_ALLOWED_ACTIONS."}
    if not approved:
        return {"success": False, "error": "Human approval is required before deployment creation."}

    normalized_batch = str(batch or "").strip().lower()
    if normalized_batch not in PATCH_BATCHES:
        return {"success": False, "error": f"Unsupported patch batch: {batch!r}."}
    if collection not in _client(client).list_collections():
        return {"success": False, "error": f"Collection {collection!r} is not allowlisted."}
    try:
        available = datetime.fromisoformat(str(available_at).replace("Z", "+00:00"))
        deadline = datetime.fromisoformat(str(deadline_at).replace("Z", "+00:00"))
    except ValueError:
        return {"success": False, "error": "available_at and deadline_at must be ISO-8601 timestamps."}
    if deadline <= available:
        return {"success": False, "error": "Deployment deadline must be after its availability time."}
    if allow_reboot and not config.SCCM_ALLOW_REBOOT:
        return {"success": False, "error": "Server reboot is disabled by SCCM_ALLOW_REBOOT."}

    deployment = Deployment(
        deployment_id=f"SIM-{uuid4().hex[:8].upper()}",
        name=str(name).strip(), collection=collection,
        software_update_group=str(software_update_group).strip(),
        batch=normalized_batch,
        available_at=available.astimezone(timezone.utc).isoformat(),
        deadline_at=deadline.astimezone(timezone.utc).isoformat(),
        allow_reboot=bool(allow_reboot),
    )
    result = _client(client).create_deployment(deployment)
    return {"success": True, "mode": config.SCCM_MODE, "deployment": result}


def get_compliance(deployment_id, client=None):
    deployment = _client(client).get_deployment(deployment_id)
    if not deployment:
        return {"success": False, "error": f"Unknown deployment: {deployment_id}."}
    return {"success": True, "mode": config.SCCM_MODE, "deployment": deployment}

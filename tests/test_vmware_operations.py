import config
import vmware_operations


class FakeVMware:
    def __init__(self):
        self.called = None

    def describe(self):
        return {
            "product": "VMware ESXi 8.0.3", "hosts": [{"name": "esxi-lab"}],
            "datastores": [{"name": "datastore2", "free_gib": 38.3}],
            "networks": [{"name": "VM Network"}], "vms": [],
        }

    def execute(self, action, target, **params):
        self.called = (action, target, params)


def setup_function():
    vmware_operations._audit = lambda *args, **kwargs: None
    vmware_operations.ops_log.write = lambda *args, **kwargs: None


def _configure(monkeypatch, actions, dry_run=True):
    monkeypatch.setattr(config, "VMWARE_ALLOWED_ACTIONS", set(actions))
    monkeypatch.setattr(config, "VMWARE_DRY_RUN", dry_run)


def test_discovery_uses_client_boundary():
    result = vmware_operations.describe_environment(client=FakeVMware())
    assert result["product"] == "VMware ESXi 8.0.3"
    assert result["datastores"][0]["name"] == "datastore2"


def test_mutation_requires_approval(monkeypatch):
    _configure(monkeypatch, {"create_snapshot"})
    result = vmware_operations.execute(
        "create_snapshot", "linux-server", snapshot_name="before-change"
    )
    assert not result["success"]
    assert "approval" in result["error"].lower()


def test_mutation_requires_allowlist(monkeypatch):
    _configure(monkeypatch, set())
    result = vmware_operations.execute(
        "create_snapshot", "linux-server", approved=True, snapshot_name="before-change"
    )
    assert not result["success"]
    assert "VMWARE_ALLOWED_ACTIONS" in result["error"]


def test_dry_run_validates_without_calling_client(monkeypatch):
    _configure(monkeypatch, {"create_snapshot"}, dry_run=True)
    client = FakeVMware()
    result = vmware_operations.execute(
        "create_snapshot", "linux-server", approved=True,
        snapshot_name="before-change", client=client,
    )
    assert result["success"] and result["dry_run"]
    assert client.called is None


def test_live_snapshot_calls_client(monkeypatch):
    _configure(monkeypatch, {"create_snapshot"}, dry_run=False)
    client = FakeVMware()
    result = vmware_operations.execute(
        "create_snapshot", "linux-server", approved=True,
        snapshot_name="before-change", client=client,
    )
    assert result["success"] and not result["dry_run"]
    assert client.called[0:2] == ("create_snapshot", "linux-server")


def test_resize_requires_complete_bounded_spec(monkeypatch):
    _configure(monkeypatch, {"resize_vm"})
    result = vmware_operations.execute(
        "resize_vm", "linux-server", approved=True, cpu_count=0, memory_mb=256
    )
    assert not result["success"]
    assert "CPU count" in result["error"]


def test_create_vm_and_patch_are_plan_only_in_live_mode(monkeypatch):
    _configure(monkeypatch, {"create_vm", "patch_host"}, dry_run=False)
    create = vmware_operations.execute(
        "create_vm", "new-linux", approved=True, vm_name="new-linux",
        guest_id="ubuntu64Guest", datastore="datastore2", network="VM Network",
        disk_gib=20, memory_mb=2048, cpu_count=2,
    )
    patch = vmware_operations.execute(
        "patch_host", "host", approved=True, patch_baseline="approved-8.0u3"
    )
    assert not create["success"] and "plan-only" in create["error"]
    assert not patch["success"] and "plan-only" in patch["error"]


def test_inventory_sync_uses_relational_tables(monkeypatch):
    statements = []

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, statement, params=None):
            statements.append((statement, params))

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def cursor(self):
            return FakeCursor()

        def commit(self):
            pass

    monkeypatch.setattr(vmware_operations.database, "initialize", lambda: None)
    monkeypatch.setattr(vmware_operations.database, "connect", lambda: FakeConnection())
    result = vmware_operations.sync_inventory({
        "endpoint": "esxi.lab", "product": "VMware ESXi", "hosts": [{"name": "host-1"}],
        "datastores": [{"name": "datastore2"}], "networks": [{"name": "VM Network"}],
        "vms": [{"name": "linux-1"}],
    })
    sql = "\n".join(item[0] for item in statements)
    assert result == {"endpoint": "esxi.lab", "hosts": 1, "datastores": 1, "networks": 1, "vms": 1}
    for table in ("vmware_endpoints", "vmware_hosts", "vmware_datastores", "vmware_networks", "vmware_virtual_machines"):
        assert table in sql

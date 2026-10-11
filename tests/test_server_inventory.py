import server_inventory


RECORDS = [
    server_inventory._normalize({"server_name":"aws-api","ip_address":"10.0.0.10","vm_type":"aws",
        "os_type":"linux","application":"Orders","enabled":True,"aws_instance_id":"i-0123456789abcdef0"}),
    server_inventory._normalize({"server_name":"vmware-web","ip_address":"10.0.0.20","vm_type":"vmware",
        "os_type":"windows","application":"Portal","enabled":True}),
]


def _use_postgresql_records(monkeypatch):
    monkeypatch.setattr(server_inventory, "_load_postgresql", lambda force=False: [dict(row) for row in RECORDS])


def test_load_uses_postgresql_only(monkeypatch):
    _use_postgresql_records(monkeypatch)
    assert [row["server_name"] for row in server_inventory.load(force=True)] == ["aws-api", "vmware-web"]
    assert server_inventory.source_status()["source"] == "postgresql"


def test_exact_lookup(monkeypatch):
    _use_postgresql_records(monkeypatch)
    assert server_inventory.get("10.0.0.10")["server_name"] == "aws-api"
    assert server_inventory.get("i-0123456789abcdef0")["server_name"] == "aws-api"


def test_ranked_search(monkeypatch):
    _use_postgresql_records(monkeypatch)
    assert server_inventory.search("Orders AWS")[0]["server_name"] == "aws-api"


def test_database_failure_has_no_file_fallback(monkeypatch):
    monkeypatch.setattr(server_inventory, "_load_postgresql", lambda force=False: (_ for _ in ()).throw(RuntimeError("offline")))
    try:
        server_inventory.load(force=True)
    except RuntimeError as exc:
        assert "no local fallback" in str(exc)
    else:
        raise AssertionError("PostgreSQL failure must be explicit")

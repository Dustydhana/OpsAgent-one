"""API contract tests preventing cross-organization data access.

These tests deliberately switch only the authenticated identity. Tenant scope must
always come from the signed token context and be forwarded to every data store.
"""
import pytest
from fastapi.testclient import TestClient

from backend import main


ORG_A = "org-tenant-a"
ORG_B = "org-tenant-b"


@pytest.fixture
def tenant_client():
    state = {"organization_id": ORG_A}

    def authenticated_user():
        return {
            "username": "tenant-admin",
            "display_name": "Tenant Admin",
            "role": "Admin",
            "organization_role": "Owner",
            "organization_id": state["organization_id"],
        }

    main.app.dependency_overrides[main.current_user] = authenticated_user
    client = TestClient(main.app)
    try:
        yield client, state
    finally:
        main.app.dependency_overrides.clear()


def test_inventory_and_dashboard_use_authenticated_organization(monkeypatch, tenant_client):
    client, identity = tenant_client
    calls = []

    def load(*, force=False, include_disabled=False, organization_id=None):
        calls.append(organization_id)
        return [{
            "server_name": f"server-{organization_id}", "ip_address": "10.0.0.1",
            "status": "running", "enabled": True, "vm_type": "aws",
            "environment": "test", "os_type": "linux", "os_version": "Ubuntu",
            "application": "App", "application_team": "Team", "server_team": "Infra",
            "important_services": [], "tags": [], "aliases": [],
        }]

    monkeypatch.setattr(main.server_inventory, "load", load)
    assert client.get("/api/v1/inventory/servers").json()[0]["server_name"] == f"server-{ORG_A}"
    identity["organization_id"] = ORG_B
    assert client.get("/api/v1/dashboard/summary").status_code == 200
    assert calls == [ORG_A, ORG_B]


def test_chat_history_cannot_cross_tenants(monkeypatch, tenant_client):
    client, identity = tenant_client
    sessions = {
        ORG_A: [{"session_id": "CHAT-A", "title": "A", "persona": "Ops", "updated_at": None}],
        ORG_B: [{"session_id": "CHAT-B", "title": "B", "persona": "Ops", "updated_at": None}],
    }

    monkeypatch.setattr(main.chat_store, "sessions",
        lambda requester, limit=50, organization_id=None: sessions[organization_id])
    monkeypatch.setattr(main.chat_store, "messages",
        lambda session_id, requester, organization_id=None: ([{"role": "user", "content": organization_id}]
            if session_id == f"CHAT-{organization_id[-1]}" else []))

    assert client.get("/api/v1/chat/sessions").json()[0]["session_id"] == "CHAT-A"
    assert client.get("/api/v1/chat/sessions/CHAT-B").json() == []
    identity["organization_id"] = ORG_B
    assert client.get("/api/v1/chat/sessions").json()[0]["session_id"] == "CHAT-B"
    assert client.get("/api/v1/chat/sessions/CHAT-A").json() == []


def test_alert_log_and_usage_routes_forward_tenant(monkeypatch, tenant_client):
    client, identity = tenant_client
    seen = []
    monkeypatch.setattr(main.alert_metrics, "summary", lambda hours, organization_id=None: seen.append(("slack", organization_id)) or {})
    monkeypatch.setattr(main.alert_metrics, "recent_alerts", lambda hours, limit, organization_id=None: [])
    monkeypatch.setattr(main.email_metrics, "summary", lambda hours, organization_id=None: seen.append(("gmail", organization_id)) or {})
    monkeypatch.setattr(main.email_metrics, "recent_messages", lambda hours, limit, organization_id=None: [])
    monkeypatch.setattr(main.ops_log, "recent", lambda **kwargs: seen.append(("logs", kwargs["organization_id"])) or [])
    monkeypatch.setattr(main.ai_usage, "summary", lambda hours, organization_id=None: seen.append(("usage", organization_id)) or {})

    for path in ("/api/v1/alerts/slack", "/api/v1/alerts/gmail", "/api/v1/logs", "/api/v1/usage/summary"):
        assert client.get(path).status_code == 200
    identity["organization_id"] = ORG_B
    assert client.get("/api/v1/alerts/slack").status_code == 200
    assert seen == [("slack", ORG_A), ("gmail", ORG_A), ("logs", ORG_A), ("usage", ORG_A), ("slack", ORG_B)]


def test_sccm_and_cloud_audits_forward_tenant(monkeypatch, tenant_client):
    client, identity = tenant_client
    seen = []
    monkeypatch.setattr(main.sccm_patch_pipeline, "list_cycles",
        lambda organization_id=None: seen.append(("sccm", organization_id)) or [])
    monkeypatch.setattr(main.aws, "audit_summary", lambda hours, organization_id=None: seen.append(("aws", organization_id)) or {})
    monkeypatch.setattr(main.aws, "audit_recent", lambda hours, limit, organization_id=None: [])
    monkeypatch.setattr(main.vmware_operations, "audit_summary", lambda hours, organization_id=None: seen.append(("vmware", organization_id)) or {})
    monkeypatch.setattr(main.vmware_operations, "audit_recent", lambda hours, limit, organization_id=None: [])

    for path in ("/api/v1/sccm/patch-cycles", "/api/v1/operations/aws/audit", "/api/v1/operations/vmware/audit"):
        assert client.get(path).status_code == 200
    identity["organization_id"] = ORG_B
    assert client.get("/api/v1/sccm/patch-cycles").status_code == 200
    assert seen == [("sccm", ORG_A), ("aws", ORG_A), ("vmware", ORG_A), ("sccm", ORG_B)]


def test_connections_and_gateways_use_token_tenant(monkeypatch, tenant_client):
    client, identity = tenant_client
    monkeypatch.setattr(main.integration_store, "list_connections",
        lambda organization_id: [{"organization_id": organization_id}])
    monkeypatch.setattr(main.integration_store, "list_gateways",
        lambda organization_id: [{"organization_id": organization_id}])

    assert client.get("/api/v1/integrations/connections").json()[0]["organization_id"] == ORG_A
    identity["organization_id"] = ORG_B
    assert client.get("/api/v1/gateways").json()[0]["organization_id"] == ORG_B

import connector_readiness


def test_readiness_reports_missing_configuration_without_secret_values(monkeypatch):
    monkeypatch.setattr(connector_readiness.integration_store, "list_connections", lambda organization_id: [])
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client-id-secret-value")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "client-secret-value")
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)

    result = connector_readiness.get_readiness("org-test")
    serialized = str(result)

    google = next(item for item in result["providers"] if item["id"] == "google")
    aws = next(item for item in result["providers"] if item["id"] == "aws")
    assert google["status"] == "ready"
    assert aws["status"] == "attention"
    assert "AWS service identity" in aws["missing"]
    assert "client-id-secret-value" not in serialized
    assert "client-secret-value" not in serialized


def test_registered_connection_is_scoped_and_ready(monkeypatch):
    monkeypatch.setattr(
        connector_readiness.integration_store,
        "list_connections",
        lambda organization_id: [{"provider": "vmware", "status": "configured"}],
    )

    result = connector_readiness.get_readiness("org-a")
    vmware = next(item for item in result["providers"] if item["id"] == "vmware")
    assert vmware["status"] == "ready"
    assert vmware["configured_connections"] == 1
    assert vmware["missing"] == []

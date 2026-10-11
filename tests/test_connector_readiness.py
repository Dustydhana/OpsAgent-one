import connector_readiness


def test_readiness_reports_missing_configuration_without_secret_values(monkeypatch):
    monkeypatch.setattr(connector_readiness.integration_store, "list_connections", lambda organization_id: [])
    monkeypatch.setenv("SLACK_BOT_TOKEN", "bot-token-secret-value")
    monkeypatch.setenv("SLACK_APP_TOKEN", "app-token-secret-value")
    monkeypatch.setenv("SLACK_CHANNEL", "operations")
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)

    result = connector_readiness.get_readiness("org-test")
    serialized = str(result)

    slack = next(item for item in result["providers"] if item["id"] == "slack")
    aws = next(item for item in result["providers"] if item["id"] == "aws")
    assert slack["status"] == "ready"
    assert aws["status"] == "attention"
    assert "AWS service identity" in aws["missing"]
    assert "bot-token-secret-value" not in serialized
    assert "app-token-secret-value" not in serialized


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

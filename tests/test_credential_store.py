import credential_store


def test_payload_encryption_is_tenant_scoped_and_does_not_contain_plaintext(monkeypatch):
    monkeypatch.setenv("OPSAGENT_CREDENTIAL_MASTER_KEY", "test-master-key-with-more-than-32-characters")
    payload = {"username": "operator", "password": "very-secret-password"}
    encrypted = credential_store.encrypt_payload("org-a", payload)

    assert "operator" not in encrypted
    assert "very-secret-password" not in encrypted
    assert credential_store.decrypt_payload("org-a", encrypted) == payload


def test_other_tenant_cannot_decrypt_payload(monkeypatch):
    monkeypatch.setenv("OPSAGENT_CREDENTIAL_MASTER_KEY", "test-master-key-with-more-than-32-characters")
    encrypted = credential_store.encrypt_payload("org-a", {"token": "secret"})

    try:
        credential_store.decrypt_payload("org-b", encrypted)
        assert False, "cross-tenant decryption must fail"
    except credential_store.CredentialVaultUnavailable:
        pass


def test_short_master_key_is_rejected(monkeypatch):
    monkeypatch.setenv("OPSAGENT_CREDENTIAL_MASTER_KEY", "too-short")
    try:
        credential_store.encrypt_payload("org-a", {"token": "secret"})
        assert False, "short keys must fail"
    except credential_store.CredentialVaultUnavailable:
        pass


def test_slack_credentials_require_tokens_channels_and_approvers():
    try:
        credential_store._validate_provider_credentials("slack", {"bot_token": "xoxb-test"})
        assert False, "incomplete Slack credentials must fail"
    except ValueError as error:
        assert "app_token" in str(error)
        assert "channels" in str(error)
        assert "approvers" in str(error)


def test_slack_token_prefixes_are_validated():
    try:
        credential_store._validate_provider_credentials("slack", {
            "bot_token": "wrong", "app_token": "xapp-test",
            "channels": "C123", "approvers": "U123",
        })
        assert False, "invalid Slack token prefix must fail"
    except ValueError as error:
        assert "xoxb-" in str(error)


def test_gmail_requires_workflow_allowlists():
    try:
        credential_store._validate_provider_credentials("gmail", {
            "username": "ops@example.com", "app_password": "secret", "imap_host": "imap.gmail.com"
        })
        assert False, "expected missing workflow fields"
    except ValueError as error:
        assert "approvers" in str(error)


def test_gmail_validates_email_allowlists():
    try:
        credential_store._validate_provider_credentials("gmail", {
            "username": "ops@example.com", "app_password": "secret", "imap_host": "imap.gmail.com",
            "request_senders": "not-an-email", "approvers": "lead@example.com",
        })
        assert False, "expected invalid sender"
    except ValueError as error:
        assert "Request Senders" in str(error)


def test_ai_configuration_status_never_returns_the_api_key(monkeypatch):
    monkeypatch.setattr(credential_store, "resolve_ai_configuration", lambda _organization_id: {
        "mode": "byok", "provider": "openai", "model": "gpt-test", "api_key": "secret-key",
    })

    status = credential_store.ai_configuration_status("org-a")

    assert status["ready"] is True
    assert status["api_key_configured"] is True
    assert "api_key" not in status

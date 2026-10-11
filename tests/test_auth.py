import auth


def test_password_hash_uses_random_salt_and_verifies():
    first_hash, first_salt = auth._password_parts("demo-admin", "LongSecurePassphrase!42")
    second_hash, second_salt = auth._password_parts("demo-admin", "LongSecurePassphrase!42")
    assert first_salt != second_salt
    assert first_hash != second_hash
    assert auth._derive_password("LongSecurePassphrase!42", first_salt) == first_hash


def test_password_policy_rejects_short_or_username_passwords():
    for password in ("short", "demo-admin-password-123"):
        try:
            auth._password_parts("demo-admin", password)
        except ValueError:
            pass
        else:
            raise AssertionError("Weak password should have been rejected")


def test_role_cloud_permissions():
    viewer = {"role": "Viewer"}
    operator = {"role": "Operator"}
    admin = {"role": "Admin"}
    assert not auth.can_cloud_action("start_instance", viewer)
    assert auth.can_cloud_action("start_instance", operator)
    assert not auth.can_cloud_action("delete_volume", operator)
    assert not auth.can_cloud_action("terminate_instance", operator)
    assert auth.can_cloud_action("delete_volume", admin)


def test_self_signup_is_disabled_by_default(monkeypatch):
    monkeypatch.setattr(auth.config, "APP_SIGNUP_ENABLED", False)
    try:
        auth.signup_user("new-viewer", "LongSecurePassphrase!42")
    except PermissionError:
        pass
    else:
        raise AssertionError("Disabled self-signup must reject account creation")


def test_self_signup_can_only_create_viewer(monkeypatch):
    captured = {}
    monkeypatch.setattr(auth.config, "APP_SIGNUP_ENABLED", True)

    def fake_create(username, password, role, **kwargs):
        captured.update(username=username, password=password, role=role, **kwargs)
        return {"username": username, "display_name": kwargs["display_name"], "role": role}

    monkeypatch.setattr(auth, "create_user", fake_create)
    created = auth.signup_user(
        "new-viewer", "LongSecurePassphrase!42", display_name="New Viewer"
    )
    assert created["role"] == "Viewer"
    assert captured["created_by"] == "self-signup"

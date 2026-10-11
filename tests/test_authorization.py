import pytest

from backend import authorization


@pytest.mark.parametrize("role", ["Owner", "Admin"])
def test_administrators_receive_all_permissions(role):
    user = {"organization_id": "org-test", "organization_role": role, "role": "Viewer"}
    assert authorization.permissions_for(user) == authorization.ALL_PERMISSIONS


def test_operator_can_execute_but_cannot_approve_or_manage_connectors():
    user = {"organization_id": "org-test", "organization_role": "Operator"}
    assert authorization.allowed(user, authorization.READ)
    assert authorization.allowed(user, authorization.OPERATE)
    assert not authorization.allowed(user, authorization.APPROVE)
    assert not authorization.allowed(user, authorization.MANAGE_CONNECTORS)


def test_approver_cannot_execute_operations():
    user = {"organization_id": "org-test", "organization_role": "Approver"}
    assert authorization.allowed(user, authorization.APPROVE)
    assert not authorization.allowed(user, authorization.OPERATE)


def test_auditor_is_read_only_with_audit_access():
    user = {"organization_id": "org-test", "organization_role": "Auditor"}
    assert authorization.allowed(user, authorization.READ)
    assert authorization.allowed(user, authorization.VIEW_AUDIT)
    assert not authorization.allowed(user, authorization.OPERATE)


def test_organization_role_overrides_legacy_application_role():
    user = {"organization_id": "org-test", "organization_role": "Viewer", "role": "Admin"}
    assert authorization.role_for(user) == "Viewer"
    assert not authorization.allowed(user, authorization.OPERATE)


def test_unscoped_request_is_rejected():
    with pytest.raises(PermissionError):
        authorization.require_organization({"organization_role": "Owner"})

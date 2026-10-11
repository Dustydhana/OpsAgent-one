"""Central enterprise authorization policy.

Organization roles are authoritative.  The legacy application role is used only
for accounts that have not yet been migrated into an organization.
"""

READ = "read"
OPERATE = "operate"
APPROVE = "approve"
MANAGE_CONNECTORS = "manage_connectors"
MANAGE_MEMBERS = "manage_members"
VIEW_AUDIT = "view_audit"
MANAGE_ORGANIZATION = "manage_organization"

ALL_PERMISSIONS = frozenset({
    READ,
    OPERATE,
    APPROVE,
    MANAGE_CONNECTORS,
    MANAGE_MEMBERS,
    VIEW_AUDIT,
    MANAGE_ORGANIZATION,
})

ROLE_PERMISSIONS = {
    "Owner": ALL_PERMISSIONS,
    "Admin": ALL_PERMISSIONS,
    "Operator": frozenset({READ, OPERATE, VIEW_AUDIT}),
    "Approver": frozenset({READ, APPROVE, VIEW_AUDIT}),
    "Auditor": frozenset({READ, VIEW_AUDIT}),
    "Viewer": frozenset({READ}),
}


def role_for(user: dict | None) -> str:
    """Return the tenant role, falling back to the legacy application role."""
    if not user:
        return ""
    return str(user.get("organization_role") or user.get("role") or "")


def permissions_for(user: dict | None) -> frozenset[str]:
    return ROLE_PERMISSIONS.get(role_for(user), frozenset())


def allowed(user: dict | None, permission: str) -> bool:
    return permission in permissions_for(user)


def require_organization(user: dict | None) -> str:
    """Return the active tenant id or reject an unsafe unscoped request."""
    organization_id = str((user or {}).get("organization_id") or "").strip()
    if not organization_id:
        raise PermissionError("An active organization is required")
    return organization_id

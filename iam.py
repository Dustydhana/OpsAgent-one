"""Organization-scoped identity and access management."""
import hashlib
import json
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
import database

ROLES = ("Owner", "Admin", "Operator", "Approver", "Viewer", "Auditor")

def _slug(value):
    base = re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")[:48] or "organization"
    return f"{base}-{secrets.token_hex(3)}"

def _effective_role(role):
    if role in {"Owner", "Admin"}: return "Admin"
    if role in {"Operator", "Approver"}: return "Operator"
    return "Viewer"

def _audit(cursor, organization_id, actor, action, target=None, details=None):
    cursor.execute("""INSERT INTO ops_agent.organization_audit
        (organization_id,actor,action,target,details) VALUES (%s,%s,%s,%s,%s::jsonb)""",
        (organization_id, actor, action, target, json.dumps(details or {})))

def memberships(username):
    database.initialize()
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""SELECT o.organization_id,o.name,o.slug,m.role,m.status
                FROM ops_agent.organization_memberships m JOIN ops_agent.organizations o USING(organization_id)
                WHERE m.username=%s AND o.enabled IS TRUE ORDER BY m.joined_at""", (username,))
            rows = cursor.fetchall()
    return [{"organization_id":r[0],"name":r[1],"slug":r[2],"organization_role":r[3],"status":r[4]} for r in rows]

def create_organization(username, name):
    organization_id=f"org-{uuid.uuid4().hex}"; slug=_slug(name)
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""INSERT INTO ops_agent.organizations(organization_id,name,slug,created_by)
                VALUES (%s,%s,%s,%s)""", (organization_id,str(name).strip()[:120],slug,username))
            cursor.execute("""INSERT INTO ops_agent.organization_memberships(organization_id,username,role)
                VALUES (%s,%s,'Owner')""", (organization_id,username))
            _audit(cursor,organization_id,username,"organization_created",organization_id,{"name":name})
        connection.commit()
    return memberships(username)[-1]

def ensure_default(user):
    existing=memberships(user["username"])
    if existing: return existing[0]
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM ops_agent.external_identities WHERE username=%s LIMIT 1", (user["username"],))
            external = cursor.fetchone() is not None
    if external:
        return create_organization(user["username"], f"{user['display_name']}'s Organization")
    organization_id="org-default"
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""INSERT INTO ops_agent.organizations(organization_id,name,slug,created_by)
                VALUES (%s,'OpsAgent Technologies','opsagent-technologies','legacy-migration') ON CONFLICT DO NOTHING""", (organization_id,))
            role="Owner" if user.get("role")=="Admin" else (user.get("role") or "Viewer")
            cursor.execute("""INSERT INTO ops_agent.organization_memberships(organization_id,username,role)
                VALUES (%s,%s,%s) ON CONFLICT DO NOTHING""", (organization_id,user["username"],role))
        connection.commit()
    return memberships(user["username"])[0]

def ensure_external_owner(user):
    existing=memberships(user["username"])
    return existing[0] if existing else create_organization(user["username"], f"{user['display_name']}'s Organization")

def accept_pending_invitations(user, email):
    """Accept valid invitations after the identity provider verifies the same email."""
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""SELECT invitation_id,organization_id,role FROM ops_agent.organization_invitations
                WHERE lower(email)=lower(%s) AND status='pending' AND expires_at>NOW() FOR UPDATE""", (email,))
            invitations=cursor.fetchall()
            for invitation_id,organization_id,role in invitations:
                cursor.execute("""INSERT INTO ops_agent.organization_memberships(organization_id,username,role)
                    VALUES (%s,%s,%s) ON CONFLICT(organization_id,username) DO NOTHING""", (organization_id,user["username"],role))
                cursor.execute("""UPDATE ops_agent.organization_invitations SET status='accepted',accepted_by=%s,
                    accepted_at=NOW() WHERE invitation_id=%s""", (user["username"],invitation_id))
                _audit(cursor,organization_id,user["username"],"invitation_accepted",invitation_id,{"email":email,"role":role})
        connection.commit()
    return memberships(user["username"])

def context(user, organization_id=None):
    items=memberships(user["username"])
    if not items: items=[ensure_default(user)]
    selected=next((x for x in items if x["organization_id"]==organization_id),items[0])
    if selected["status"]!="active": raise PermissionError("Organization membership is suspended")
    return {**user,**selected,"role":_effective_role(selected["organization_role"]),"organizations":items}

def list_members(organization_id):
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""SELECT u.username,u.display_name,m.role,m.status,m.joined_at,u.last_login_at
                FROM ops_agent.organization_memberships m JOIN ops_agent.app_users u USING(username)
                WHERE m.organization_id=%s ORDER BY u.display_name""",(organization_id,));rows=cursor.fetchall()
    return [{"username":r[0],"display_name":r[1],"role":r[2],"status":r[3],"joined_at":r[4],"last_login_at":r[5]} for r in rows]

def update_member(organization_id, username, role, status, actor):
    if role not in ROLES or status not in {"active","suspended"}: raise ValueError("Invalid membership role or status")
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT role,status FROM ops_agent.organization_memberships WHERE organization_id=%s AND username=%s FOR UPDATE",(organization_id,username));before=cursor.fetchone()
            if not before: raise ValueError("Membership not found")
            if before[0]=="Owner" and (role!="Owner" or status!="active"):
                cursor.execute("SELECT COUNT(*) FROM ops_agent.organization_memberships WHERE organization_id=%s AND role='Owner' AND status='active'",(organization_id,))
                if cursor.fetchone()[0]<=1: raise ValueError("The last active Owner cannot be changed")
            cursor.execute("UPDATE ops_agent.organization_memberships SET role=%s,status=%s,updated_at=NOW() WHERE organization_id=%s AND username=%s",(role,status,organization_id,username))
            _audit(cursor,organization_id,actor,"membership_updated",username,{"previous_role":before[0],"role":role,"status":status})
        connection.commit()

def add_member(organization_id, username, role, actor):
    """Add an existing local application user to an organization."""
    if role not in set(ROLES)-{"Owner"}:
        raise ValueError("Invalid organization role")
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM ops_agent.app_users WHERE username=%s", (username,))
            if not cursor.fetchone():
                raise ValueError("Application user not found")
            cursor.execute("""INSERT INTO ops_agent.organization_memberships
                (organization_id,username,role) VALUES (%s,%s,%s)""",
                (organization_id,username,role))
            _audit(cursor,organization_id,actor,"member_created",username,{"role":role})
        connection.commit()

def invite(organization_id,email,role,actor):
    if role not in set(ROLES)-{"Owner"}: raise ValueError("Invalid invitation role")
    token=secrets.token_urlsafe(32); invitation_id=f"inv-{uuid.uuid4().hex}"
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""INSERT INTO ops_agent.organization_invitations
                (invitation_id,organization_id,email,role,token_hash,invited_by,expires_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s)""",(invitation_id,organization_id,email.lower(),role,hashlib.sha256(token.encode()).hexdigest(),actor,datetime.now(timezone.utc)+timedelta(days=7)))
            _audit(cursor,organization_id,actor,"member_invited",email,{"role":role})
        connection.commit()
    return {"invitation_id":invitation_id,"token":token,"expires_in_days":7}

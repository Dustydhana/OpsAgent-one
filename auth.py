"""PostgreSQL-backed authentication and role authorization for Streamlit."""

import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta, timezone

import database
import ops_log
import config
import pyotp
from backend import security


ROLES = ("Admin", "Operator", "Viewer")
_ADMIN_ONLY_CLOUD_ACTIONS = {
    "delete_snapshot", "delete_volume", "detach_secondary_nic", "terminate_instance",
    "remove_snapshot", "enter_maintenance", "exit_maintenance", "reboot_host",
    "shutdown_host", "patch_host", "create_vm", "provision_instance",
}
_MAX_FAILED_ATTEMPTS = 5
_LOCK_MINUTES = 15
_SCRYPT_N = 2 ** 14
_SCRYPT_R = 8
_SCRYPT_P = 1


def _normalize_username(username):
    value = str(username or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{2,63}", value):
        raise ValueError("Username must be 3-64 characters using letters, numbers, dot, underscore, or hyphen")
    return value


def _normalize_role(role):
    value = next((item for item in ROLES if item.casefold() == str(role or "").casefold()), None)
    if not value:
        raise ValueError(f"Role must be one of: {', '.join(ROLES)}")
    return value


def _validate_password(username, password):
    value = str(password or "")
    if len(value) < 12:
        raise ValueError("Password must contain at least 12 characters")
    if len(value) > 256:
        raise ValueError("Password is too long")
    if username.casefold() in value.casefold():
        raise ValueError("Password must not contain the username")
    return value


def _derive_password(password, salt):
    return hashlib.scrypt(
        str(password).encode("utf-8"), salt=bytes(salt),
        n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32,
    )


def _password_parts(username, password):
    value = _validate_password(username, password)
    salt = secrets.token_bytes(16)
    return _derive_password(value, salt), salt


def _write_user_audit(cursor, actor, action, target, previous_role=None, new_role=None, details=None):
    cursor.execute("""INSERT INTO ops_agent.app_user_audit
        (actor,action,target_username,previous_role,new_role,details)
        VALUES (%s,%s,%s,%s,%s,%s)""",
        (actor, action, target, previous_role, new_role, details))


def user_count():
    database.initialize()
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM ops_agent.app_users")
            return int(cursor.fetchone()[0])


def create_user(username, password, role, *, display_name="", created_by="bootstrap"):
    username = _normalize_username(username)
    role = _normalize_role(role)
    password_hash, password_salt = _password_parts(username, password)
    display_name = str(display_name or username).strip()[:120]
    database.initialize()
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM ops_agent.app_users")
            if cursor.fetchone()[0] == 0 and role != "Admin":
                raise ValueError("The first application user must have the Admin role")
            cursor.execute("""INSERT INTO ops_agent.app_users
                (username,display_name,role,password_hash,password_salt,created_by)
                VALUES (%s,%s,%s,%s,%s,%s)""",
                (username, display_name, role, password_hash, password_salt, created_by))
            _write_user_audit(cursor, created_by, "user_created", username, new_role=role)
        connection.commit()
    ops_log.write("auth", "INFO", "user_created", f"username={username}; role={role}")
    return get_user(username)


def signup_user(username, password, *, display_name=""):
    """Create a least-privilege self-service account when explicitly enabled."""
    if not config.APP_SIGNUP_ENABLED:
        raise PermissionError("Self-service sign-up is disabled")
    # create_user enforces that an empty database can only be bootstrapped with
    # an Admin, so public sign-up can never seize the first administrator role.
    return create_user(
        username, password, "Viewer", display_name=display_name,
        created_by="self-signup",
    )


def get_user(username):
    try:
        username = _normalize_username(username)
    except ValueError:
        return None
    database.initialize()
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""SELECT username,display_name,role,enabled,failed_attempts,
                locked_until,last_login_at,created_at,updated_at
                FROM ops_agent.app_users WHERE username=%s""", (username,))
            row = cursor.fetchone()
    if not row:
        return None
    return {
        "username": row[0], "display_name": row[1], "role": row[2], "enabled": row[3],
        "failed_attempts": row[4], "locked_until": row[5], "last_login_at": row[6],
        "created_at": row[7], "updated_at": row[8],
    }


def mfa_status(username):
    username = _normalize_username(username)
    database.initialize()
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT mfa_enabled FROM ops_agent.app_users WHERE username=%s", (username,))
            row = cursor.fetchone()
    return {"enabled": bool(row and row[0])}


def begin_mfa_setup(username):
    username = _normalize_username(username)
    secret = pyotp.random_base32()
    encrypted = security.encrypt_secret(secret)
    database.initialize()
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("UPDATE ops_agent.app_users SET mfa_secret_encrypted=%s,mfa_enabled=FALSE,updated_at=NOW() WHERE username=%s", (encrypted, username))
            _write_user_audit(cursor, username, "mfa_setup_started", username)
        connection.commit()
    return {"secret": secret, "otpauth_uri": pyotp.TOTP(secret).provisioning_uri(name=username, issuer_name="OpsAgent One")}


def verify_mfa(username, code, *, enable=False):
    username = _normalize_username(username)
    database.initialize()
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT mfa_secret_encrypted,mfa_enabled FROM ops_agent.app_users WHERE username=%s FOR UPDATE", (username,))
            row = cursor.fetchone()
            if not row or not row[0]:
                return False
            try:
                valid = pyotp.TOTP(security.decrypt_secret(row[0])).verify(str(code or "").strip(), valid_window=1)
            except Exception:
                valid = False
            if valid and enable:
                cursor.execute("UPDATE ops_agent.app_users SET mfa_enabled=TRUE,updated_at=NOW() WHERE username=%s", (username,))
                _write_user_audit(cursor, username, "mfa_enabled", username)
        connection.commit()
    return bool(valid and (enable or row[1]))


def authenticate(username, password):
    try:
        username = _normalize_username(username)
    except ValueError:
        username = str(username or "").strip().lower()[:64]
    now = datetime.now(timezone.utc)
    database.initialize()
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""SELECT username,display_name,role,password_hash,password_salt,
                enabled,failed_attempts,locked_until FROM ops_agent.app_users
                WHERE username=%s FOR UPDATE""", (username,))
            row = cursor.fetchone()
            if not row:
                _derive_password(password or "", b"\x00" * 16)
                connection.commit()
                ops_log.write("auth", "WARNING", "login_failed", f"username={username or 'invalid'}")
                return None, "Invalid username or password"
            if not row[5]:
                connection.commit()
                ops_log.write("auth", "WARNING", "login_disabled", f"username={username}")
                return None, "Invalid username or password"
            if row[7] and row[7] > now:
                connection.commit()
                return None, "Account is temporarily locked. Try again later"
            supplied_hash = _derive_password(password or "", row[4])
            if not hmac.compare_digest(bytes(row[3]), supplied_hash):
                attempts = int(row[6] or 0) + 1
                locked_until = now + timedelta(minutes=_LOCK_MINUTES) if attempts >= _MAX_FAILED_ATTEMPTS else None
                cursor.execute("""UPDATE ops_agent.app_users SET failed_attempts=%s,
                    locked_until=%s,updated_at=NOW() WHERE username=%s""",
                    (attempts, locked_until, username))
                connection.commit()
                ops_log.write("auth", "WARNING", "login_failed", f"username={username}; attempts={attempts}")
                return None, "Invalid username or password"
            cursor.execute("""UPDATE ops_agent.app_users SET failed_attempts=0,locked_until=NULL,
                last_login_at=NOW(),updated_at=NOW() WHERE username=%s""", (username,))
        connection.commit()
    user = {"username": row[0], "display_name": row[1], "role": row[2], "enabled": True}
    ops_log.write("auth", "INFO", "login_succeeded", f"username={username}; role={row[2]}")
    return user, None


def authenticate_external(provider, subject, email, display_name):
    """Resolve or provision a least-privilege account for a verified OAuth identity."""
    provider, subject = str(provider).lower()[:40], str(subject)[:255]
    database.initialize()
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""SELECT u.username,u.display_name,u.role,u.enabled
                FROM ops_agent.external_identities e JOIN ops_agent.app_users u USING(username)
                WHERE e.provider=%s AND e.subject=%s""", (provider, subject))
            row = cursor.fetchone()
            if row:
                if not row[3]:
                    raise PermissionError("Account is disabled")
                cursor.execute("""UPDATE ops_agent.external_identities SET last_login_at=NOW(),email=%s
                    WHERE provider=%s AND subject=%s""", (email, provider, subject))
                connection.commit()
                return {"username": row[0], "display_name": row[1], "role": row[2], "enabled": True}
    base = re.sub(r"[^a-z0-9._-]", "", str(email or f"{provider}.{subject}").split("@")[0].lower())[:52]
    base = base if len(base) >= 3 else f"{provider}.user"
    username = base
    suffix = 1
    while get_user(username):
        suffix += 1
        username = f"{base[:55]}.{suffix}"
    user = create_user(username, secrets.token_urlsafe(32), "Viewer", display_name=display_name or email or username, created_by=f"oauth:{provider}")
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""INSERT INTO ops_agent.external_identities(provider,subject,username,email)
                VALUES (%s,%s,%s,%s) ON CONFLICT(provider,subject) DO UPDATE SET
                last_login_at=NOW(),email=EXCLUDED.email""", (provider, subject, username, email))
        connection.commit()
    return user


def list_users():
    database.initialize()
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""SELECT username,display_name,role,enabled,failed_attempts,
                locked_until,last_login_at,created_at FROM ops_agent.app_users ORDER BY username""")
            rows = cursor.fetchall()
    return [{
        "Username": row[0], "Display name": row[1], "Role": row[2], "Enabled": row[3],
        "Failed attempts": row[4], "Locked until": row[5], "Last login": row[6], "Created": row[7],
    } for row in rows]


def user_audit_recent(limit=100):
    database.initialize()
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""SELECT occurred_at,actor,action,target_username,previous_role,new_role,details
                FROM ops_agent.app_user_audit ORDER BY occurred_at DESC LIMIT %s""",
                (max(1, min(int(limit), 500)),))
            rows = cursor.fetchall()
    return [{
        "Time": row[0].astimezone().strftime("%Y-%m-%d %H:%M:%S"), "Actor": row[1],
        "Action": row[2], "Target": row[3], "Previous role": row[4] or "",
        "New role": row[5] or "", "Details": row[6] or "",
    } for row in rows]


def update_user(username, *, role, enabled, actor):
    username = _normalize_username(username)
    role = _normalize_role(role)
    database.initialize()
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT role,enabled FROM ops_agent.app_users WHERE username=%s FOR UPDATE", (username,))
            previous = cursor.fetchone()
            if not previous:
                raise ValueError("User was not found")
            if previous[0] == "Admin" and previous[1] and (role != "Admin" or not enabled):
                cursor.execute("SELECT COUNT(*) FROM ops_agent.app_users WHERE role='Admin' AND enabled IS TRUE")
                if cursor.fetchone()[0] <= 1:
                    raise ValueError("The last enabled Admin cannot be disabled or downgraded")
            cursor.execute("""UPDATE ops_agent.app_users SET role=%s,enabled=%s,
                failed_attempts=CASE WHEN %s THEN failed_attempts ELSE 0 END,
                locked_until=CASE WHEN %s THEN locked_until ELSE NULL END,updated_at=NOW()
                WHERE username=%s""", (role, bool(enabled), bool(enabled), bool(enabled), username))
            _write_user_audit(
                cursor, actor, "user_updated", username, previous_role=previous[0], new_role=role,
                details=f"enabled={bool(enabled)}",
            )
        connection.commit()
    ops_log.write("auth", "INFO", "user_updated", f"actor={actor}; username={username}; role={role}; enabled={enabled}")


def reset_password(username, password, *, actor):
    username = _normalize_username(username)
    password_hash, password_salt = _password_parts(username, password)
    database.initialize()
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""UPDATE ops_agent.app_users SET password_hash=%s,password_salt=%s,
                failed_attempts=0,locked_until=NULL,password_changed_at=NOW(),updated_at=NOW()
                WHERE username=%s RETURNING role""", (password_hash, password_salt, username))
            row = cursor.fetchone()
            if not row:
                raise ValueError("User was not found")
            _write_user_audit(cursor, actor, "password_reset", username, new_role=row[0])
        connection.commit()
    ops_log.write("auth", "INFO", "password_reset", f"actor={actor}; username={username}")


def can_cloud_action(action, user=None):
    if not user:
        return False
    if user.get("role") == "Admin":
        return True
    if user.get("role") == "Operator":
        return action not in _ADMIN_ONLY_CLOUD_ACTIONS
    return False

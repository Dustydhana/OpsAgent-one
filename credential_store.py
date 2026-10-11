"""Encrypted, tenant-scoped connector credential storage.

The public API never exposes decrypted material. Decryption is available only
to backend connector code through ``resolve``.
"""

import base64
import hashlib
import json
import os
import uuid

from cryptography.fernet import Fernet, InvalidToken
from psycopg.rows import dict_row

import database
import integration_store


class CredentialVaultUnavailable(RuntimeError):
    pass


def _master_key() -> bytes:
    value = os.getenv("OPSAGENT_CREDENTIAL_MASTER_KEY", "").strip()
    if len(value) < 32:
        raise CredentialVaultUnavailable(
            "Credential vault is not initialized. Set OPSAGENT_CREDENTIAL_MASTER_KEY to at least 32 random characters."
        )
    return value.encode()


def _cipher(organization_id: str) -> Fernet:
    # Tenant-derived keys provide cryptographic separation while retaining one
    # rotatable platform root key outside the database.
    digest = hashlib.sha256(_master_key() + b"\x00" + organization_id.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_payload(organization_id: str, payload: dict[str, str]) -> str:
    return _cipher(organization_id).encrypt(json.dumps(payload, separators=(",", ":")).encode()).decode()


def decrypt_payload(organization_id: str, encrypted_payload: str) -> dict[str, str]:
    try:
        value = json.loads(_cipher(organization_id).decrypt(encrypted_payload.encode()).decode())
    except (InvalidToken, ValueError, json.JSONDecodeError) as error:
        raise CredentialVaultUnavailable("Credential cannot be decrypted with the active master key") from error
    if not isinstance(value, dict):
        raise CredentialVaultUnavailable("Credential payload is invalid")
    return {str(key): str(item) for key, item in value.items()}


def _safe_metadata(secrets: dict[str, str]) -> dict:
    return {"fields": sorted(secrets), "field_count": len(secrets)}


def _validate_provider_credentials(provider: str, secrets: dict[str, str]):
    required = {
        "aws": {"aws_access_key_id", "aws_secret_access_key", "region"},
        "slack": {"bot_token", "app_token", "channels", "approvers"},
        "gmail": {"username", "app_password", "imap_host", "request_senders", "approvers"},
        "vmware": {"endpoint", "username", "password"},
    }.get(provider, set())
    missing = sorted(key for key in required if not secrets.get(key, "").strip())
    if missing:
        raise ValueError(f"Missing required credential fields: {', '.join(missing)}")
    if provider == "slack":
        if not secrets["bot_token"].startswith("xoxb-"):
            raise ValueError("Slack bot token must begin with xoxb-")
        if not secrets["app_token"].startswith("xapp-"):
            raise ValueError("Slack app token must begin with xapp-")
    if provider == "gmail":
        for key in ("username", "request_senders", "approvers"):
            values = [value.strip() for value in secrets[key].split(",") if value.strip()]
            if not values or any("@" not in value or value.startswith("@") or value.endswith("@") for value in values):
                raise ValueError(f"{key.replace('_', ' ').title()} must contain valid email addresses")


def create_connection(organization_id: str, actor: str, provider: str, display_name: str,
                      connection_type: str, endpoint: str | None, configuration: dict,
                      secrets: dict[str, str]):
    if provider not in {item["id"] for item in integration_store.CATALOG}:
        raise ValueError("Unknown integration provider")
    if connection_type != "api":
        raise ValueError("Encrypted application credentials are supported for API connections")
    clean = {str(key).strip(): str(value).strip() for key, value in secrets.items() if str(value).strip()}
    if not clean or len(clean) > 20:
        raise ValueError("Provide between 1 and 20 credential fields")
    if any(not key or len(key) > 80 or len(value) > 8000 for key, value in clean.items()):
        raise ValueError("Credential field limits were exceeded")
    _validate_provider_credentials(provider, clean)
    credential_id = f"cred_{uuid.uuid4().hex}"
    connection_id = f"con_{uuid.uuid4().hex}"
    encrypted = encrypt_payload(organization_id, clean)
    reference = f"opsagent-vault://{credential_id}"
    with database.connect(row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute("""INSERT INTO ops_agent.connector_credentials
                (credential_id,organization_id,provider,name,encrypted_payload,metadata,created_by)
                VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s)""",
                (credential_id, organization_id, provider, display_name, encrypted,
                 json.dumps(_safe_metadata(clean)), actor))
            cursor.execute("""INSERT INTO ops_agent.integration_connections
                (connection_id,organization_id,provider,display_name,connection_type,status,
                 endpoint,credential_reference,configuration,created_by)
                VALUES (%s,%s,%s,%s,%s,'configured',%s,%s,%s::jsonb,%s) RETURNING *""",
                (connection_id, organization_id, provider, display_name, connection_type,
                 endpoint, reference, json.dumps(configuration), actor))
            record = cursor.fetchone()
            cursor.execute("""INSERT INTO ops_agent.organization_audit
                (organization_id,actor,action,target,details)
                VALUES (%s,%s,'connector_credential_created',%s,%s::jsonb)""",
                (organization_id, actor, credential_id,
                 json.dumps({"provider": provider, "connection_id": connection_id, "fields": sorted(clean)})))
        connection.commit()
    return record


def list_credentials(organization_id: str):
    with database.connect(row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute("""SELECT credential_id,provider,name,metadata,created_by,created_at,updated_at
                FROM ops_agent.connector_credentials WHERE organization_id=%s ORDER BY created_at DESC""",
                (organization_id,))
            return cursor.fetchall()


def resolve(organization_id: str, credential_id: str) -> dict[str, str]:
    """Backend-only secret resolution; never expose this through a route."""
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""SELECT encrypted_payload FROM ops_agent.connector_credentials
                WHERE organization_id=%s AND credential_id=%s AND status='active'""",
                (organization_id, credential_id))
            row = cursor.fetchone()
    if not row:
        raise KeyError("Credential not found")
    return decrypt_payload(organization_id, row[0])


def resolve_provider(organization_id: str, provider: str) -> dict[str, str] | None:
    """Resolve the newest active tenant credential for backend connector use."""
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""SELECT encrypted_payload FROM ops_agent.connector_credentials
                WHERE organization_id=%s AND provider=%s AND status='active'
                ORDER BY created_at DESC LIMIT 1""", (organization_id, provider))
            row = cursor.fetchone()
    return decrypt_payload(organization_id, row[0]) if row else None


def update_provider_fields(organization_id: str, actor: str, provider: str, updates: dict[str, str]):
    """Update selected fields without returning or replacing stored secrets."""
    clean = {str(key): str(value).strip() for key, value in updates.items() if str(value).strip()}
    with database.connect(row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute("""SELECT credential_id,encrypted_payload FROM ops_agent.connector_credentials
                WHERE organization_id=%s AND provider=%s AND status='active'
                ORDER BY created_at DESC LIMIT 1 FOR UPDATE""", (organization_id, provider))
            row = cursor.fetchone()
            if not row:
                raise KeyError("Credential not found")
            payload = decrypt_payload(organization_id, row["encrypted_payload"])
            payload.update(clean)
            _validate_provider_credentials(provider, payload)
            cursor.execute("""UPDATE ops_agent.connector_credentials SET encrypted_payload=%s,
                metadata=%s::jsonb,updated_at=NOW() WHERE credential_id=%s AND organization_id=%s""",
                (encrypt_payload(organization_id, payload), json.dumps(_safe_metadata(payload)),
                 row["credential_id"], organization_id))
            cursor.execute("""INSERT INTO ops_agent.organization_audit
                (organization_id,actor,action,target,details)
                VALUES (%s,%s,'connector_configuration_updated',%s,%s::jsonb)""",
                (organization_id, actor, row["credential_id"],
                 json.dumps({"provider": provider, "fields": sorted(clean)})))
        connection.commit()
    return {"provider": provider, "updated_fields": sorted(clean)}


def disconnect_provider(organization_id: str, actor: str, provider: str):
    """Revoke active credentials while retaining connector and audit history."""
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""UPDATE ops_agent.connector_credentials SET status='revoked',updated_at=NOW()
                WHERE organization_id=%s AND provider=%s AND status='active'""", (organization_id, provider))
            revoked = cursor.rowcount
            cursor.execute("""UPDATE ops_agent.integration_connections SET status='disconnected',
                updated_at=NOW() WHERE organization_id=%s AND provider=%s""", (organization_id, provider))
            cursor.execute("""INSERT INTO ops_agent.organization_audit
                (organization_id,actor,action,target,details)
                VALUES (%s,%s,'connector_disconnected',%s,%s::jsonb)""",
                (organization_id, actor, provider, json.dumps({"revoked_credentials": revoked})))
        connection.commit()
    return {"provider": provider, "disconnected": True, "revoked_credentials": revoked}


def delete_provider(organization_id: str, actor: str, provider: str):
    """Permanently remove stored connector credentials and registrations."""
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""DELETE FROM ops_agent.integration_connections
                WHERE organization_id=%s AND provider=%s""", (organization_id, provider))
            connections = cursor.rowcount
            cursor.execute("""DELETE FROM ops_agent.connector_credentials
                WHERE organization_id=%s AND provider=%s""", (organization_id, provider))
            credentials = cursor.rowcount
            cursor.execute("""INSERT INTO ops_agent.organization_audit
                (organization_id,actor,action,target,details)
                VALUES (%s,%s,'connector_deleted',%s,%s::jsonb)""",
                (organization_id, actor, provider,
                 json.dumps({"connections": connections, "credentials": credentials})))
        connection.commit()
    return {"provider": provider, "deleted": True, "connections": connections, "credentials": credentials}


def record_test(organization_id: str, provider: str, success: bool, error: str | None = None):
    safe_error = str(error or "")[:500] or None
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""UPDATE ops_agent.integration_connections SET status=%s,
                last_tested_at=NOW(),last_error=%s,updated_at=NOW() WHERE connection_id=(
                    SELECT connection_id FROM ops_agent.integration_connections
                    WHERE organization_id=%s AND provider=%s ORDER BY created_at DESC LIMIT 1)""",
                ("connected" if success else "attention", safe_error, organization_id, provider))
        connection.commit()

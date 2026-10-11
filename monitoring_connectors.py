"""Provider-neutral secure webhook intake for monitoring platforms."""

import hashlib
import json
import secrets
import uuid

from psycopg.rows import dict_row

import database

PROVIDERS = {"datadog", "solarwinds", "nagios"}


def register(organization_id: str, actor: str, provider: str, name: str, public_base_url: str):
    provider = provider.lower()
    if provider not in PROVIDERS:
        raise ValueError("Unsupported monitoring provider")
    connector_id = f"mon_{uuid.uuid4().hex}"
    token = secrets.token_urlsafe(40)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with database.connect(row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute("""INSERT INTO ops_agent.monitoring_connectors
                (connector_id, organization_id, provider, name, token_hash, status, created_by)
                VALUES (%s,%s,%s,%s,%s,'pending',%s)
                RETURNING connector_id, provider, name, status, created_at""",
                (connector_id, organization_id, provider, name, token_hash, actor))
            record = dict(cursor.fetchone())
        connection.commit()
    record["webhook_url"] = f"{public_base_url.rstrip('/')}/api/v1/public/integrations/monitoring/{provider}/{connector_id}/events"
    record["bearer_token"] = token
    return record


def receive(provider: str, connector_id: str, token: str, payload: dict):
    provider = provider.lower()
    supplied_hash = hashlib.sha256(token.encode()).hexdigest()
    with database.connect(row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute("""SELECT organization_id, token_hash FROM ops_agent.monitoring_connectors
                WHERE connector_id=%s AND provider=%s AND status <> 'revoked'""", (connector_id, provider))
            connector = cursor.fetchone()
            if not connector or not secrets.compare_digest(connector["token_hash"], supplied_hash):
                raise PermissionError("Invalid monitoring webhook credential")
            event_key = str(payload.get("id") or payload.get("event_id") or payload.get("alert_id") or payload.get("incident_id") or uuid.uuid4().hex)[:500]
            event_status = str(payload.get("status") or payload.get("state") or payload.get("severity") or "received").lower()[:80]
            title = str(payload.get("title") or payload.get("message") or payload.get("name") or f"{provider.title()} event")[:500]
            cursor.execute("""INSERT INTO ops_agent.monitoring_events
                (connector_id, organization_id, provider, event_key, event_status, title, payload)
                VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb) RETURNING event_id, received_at""",
                (connector_id, connector["organization_id"], provider, event_key, event_status, title, json.dumps(payload)))
            event = dict(cursor.fetchone())
            cursor.execute("""UPDATE ops_agent.monitoring_connectors SET status='connected',
                last_received_at=NOW(), updated_at=NOW() WHERE connector_id=%s""", (connector_id,))
        connection.commit()
    return {"accepted": True, "event_id": event["event_id"], "provider": provider, "status": event_status}

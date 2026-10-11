"""Secure, tenant-scoped Grafana Alerting webhook connector."""

import hashlib
import json
import secrets
import uuid

from psycopg.rows import dict_row

import database


def register(organization_id: str, actor: str, name: str, public_base_url: str):
    connector_id = f"graf_{uuid.uuid4().hex}"
    token = secrets.token_urlsafe(40)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with database.connect(row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute("""INSERT INTO ops_agent.grafana_connectors
                (connector_id, organization_id, name, token_hash, status, created_by)
                VALUES (%s,%s,%s,%s,'pending',%s)
                RETURNING connector_id, name, status, created_at""",
                (connector_id, organization_id, name, token_hash, actor))
            record = dict(cursor.fetchone())
        connection.commit()
    record["webhook_url"] = f"{public_base_url.rstrip('/')}/api/v1/public/integrations/grafana/{connector_id}/events"
    record["bearer_token"] = token
    return record


def receive(connector_id: str, token: str, payload: dict):
    supplied_hash = hashlib.sha256(token.encode()).hexdigest()
    with database.connect(row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute("""SELECT connector_id, organization_id, token_hash FROM ops_agent.grafana_connectors
                WHERE connector_id=%s AND status <> 'revoked'""", (connector_id,))
            connector = cursor.fetchone()
            if not connector or not secrets.compare_digest(connector["token_hash"], supplied_hash):
                raise PermissionError("Invalid Grafana webhook credential")
            status = str(payload.get("status") or payload.get("state") or "unknown").lower()
            title = str(payload.get("title") or payload.get("commonLabels", {}).get("alertname") or payload.get("receiver") or "Grafana alert")[:500]
            event_key = str(payload.get("groupKey") or payload.get("fingerprint") or uuid.uuid4().hex)[:500]
            cursor.execute("""INSERT INTO ops_agent.grafana_events
                (connector_id, organization_id, event_key, alert_status, title, payload)
                VALUES (%s,%s,%s,%s,%s,%s::jsonb) ON CONFLICT (connector_id,event_key,alert_status)
                DO UPDATE SET payload=EXCLUDED.payload, received_at=NOW() RETURNING event_id, received_at""",
                (connector_id, connector["organization_id"], event_key, status, title, json.dumps(payload)))
            event = dict(cursor.fetchone())
            cursor.execute("""UPDATE ops_agent.grafana_connectors SET status='connected',
                last_received_at=NOW(), updated_at=NOW() WHERE connector_id=%s""", (connector_id,))
        connection.commit()
    return {"accepted": True, "event_id": event["event_id"], "status": status}


def list_connectors(organization_id: str):
    with database.connect(row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute("""SELECT connector_id, name, status, last_received_at, created_at
                FROM ops_agent.grafana_connectors WHERE organization_id=%s ORDER BY created_at DESC""", (organization_id,))
            return cursor.fetchall()

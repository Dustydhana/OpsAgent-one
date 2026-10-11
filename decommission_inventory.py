"""PostgreSQL-backed lifecycle register for powered-off and retired servers."""

from datetime import datetime, timedelta, timezone
import json
import re

import database
import config


OFF_STATES = {"stopped", "stopping", "deallocated", "off", "poweredoff", "powered off", "terminated"}
FINAL_STATES = {"terminated", "decommissioned", "retired"}


def _ticket(record):
    resource = record.get("aws_instance_id") or record.get("server_name") or "SERVER"
    clean = re.sub(r"[^A-Za-z0-9]", "", str(resource)).upper()[-10:]
    return f"DCM-{clean}"


def _organization_id(value=None):
    organization_id = str(value or config.DEFAULT_ORGANIZATION_ID or "").strip()
    if not organization_id:
        raise PermissionError("An organization is required for decommission inventory access")
    return organization_id


def register_from_server(record, *, requester="Inventory sync", organization_id=None):
    """Create or refresh a decommission record from an authoritative server record."""
    organization_id = _organization_id(organization_id)
    state = str((record or {}).get("status") or "unknown").lower()
    if not record or state not in OFF_STATES:
        return None
    now = datetime.now(timezone.utc)
    final = state in FINAL_STATES
    lifecycle = "decommissioned" if final else "scream_test"
    owner = record.get("application_team") or record.get("server_team") or "Unknown"
    ticket = _ticket(record)
    details = {
        "environment": record.get("environment"), "application": record.get("application"),
        "server_team": record.get("server_team"), "region": record.get("aws_region"),
        "os_type": record.get("os_type"), "notes": record.get("notes"),
    }
    database.initialize()
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""INSERT INTO ops_agent.decommission_inventory
                (organization_id,server_name,provider,resource_id,ip_address,power_state,lifecycle_state,owner,
                 requested_by,ticket_reference,scream_test_started_at,scream_test_ends_at,
                 decommissioned_at,details,updated_at)
                VALUES (%s,%s,%s,NULLIF(%s,''),NULLIF(%s,''),%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,NOW())
                ON CONFLICT (server_name) DO UPDATE SET provider=EXCLUDED.provider,
                resource_id=EXCLUDED.resource_id,ip_address=EXCLUDED.ip_address,
                power_state=EXCLUDED.power_state,lifecycle_state=EXCLUDED.lifecycle_state,
                owner=EXCLUDED.owner,ticket_reference=EXCLUDED.ticket_reference,
                decommissioned_at=COALESCE(EXCLUDED.decommissioned_at,ops_agent.decommission_inventory.decommissioned_at),
                details=EXCLUDED.details,updated_at=NOW()
                RETURNING server_name,provider,resource_id,ip_address,power_state,lifecycle_state,
                owner,requested_by,ticket_reference,reason,scream_test_started_at,scream_test_ends_at,
                decommissioned_at,source,details,updated_at""", (
                organization_id, record["server_name"], record.get("vm_type") or "unknown",
                record.get("aws_instance_id") or "", record.get("ip_address") or "", state,
                lifecycle, owner, requester, ticket, now, None if final else now + timedelta(days=14),
                now if final else None, json.dumps(details),
            ))
            row = cursor.fetchone()
            columns = [item.name for item in cursor.description]
        connection.commit()
    return dict(zip(columns, row))


def get(identifier, organization_id=None):
    organization_id = _organization_id(organization_id)
    needle = str(identifier or "").strip().lower()
    if not needle:
        return None
    database.initialize()
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""SELECT server_name,provider,resource_id,ip_address,power_state,lifecycle_state,
                owner,requested_by,ticket_reference,reason,scream_test_started_at,scream_test_ends_at,
                decommissioned_at,source,details,updated_at FROM ops_agent.decommission_inventory
                WHERE organization_id=%s AND (lower(server_name)=%s OR lower(COALESCE(resource_id,''))=%s
                   OR lower(COALESCE(ip_address,''))=%s) LIMIT 1""", (organization_id, needle, needle, needle))
            row = cursor.fetchone()
            if not row:
                return None
            columns = [item.name for item in cursor.description]
            return dict(zip(columns, row))


def retrieve_for_alert(alert_text, extracted_host=None):
    """Resolve an exact decommission record by address, resource ID, or server name."""
    if extracted_host:
        exact = get(extracted_host)
        if exact:
            return exact
    text = str(alert_text or "").lower()
    for record in list_records():
        identities = (record.get("server_name"), record.get("resource_id"), record.get("ip_address"))
        if any(str(value).lower() in text for value in identities if value):
            return record
    return None


def list_records(organization_id=None):
    organization_id = _organization_id(organization_id)
    database.initialize()
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""SELECT server_name,provider,resource_id,ip_address,power_state,lifecycle_state,
                owner,requested_by,ticket_reference,reason,scream_test_started_at,scream_test_ends_at,
                decommissioned_at,source,details,updated_at FROM ops_agent.decommission_inventory
                WHERE organization_id=%s ORDER BY updated_at DESC""", (organization_id,))
            columns = [item.name for item in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

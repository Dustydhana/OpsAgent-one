"""Persistent, approval-gated SCCM monthly patch lifecycle orchestration."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from uuid import uuid4

import database
import config
import email_handler
import ops_log
import sccm_operations


STAGES = [
    ("release_intake", "Microsoft release intake", "Collect released KBs, severity, products and restart requirements."),
    ("baseline", "Build update baseline", "Create the Software Update Group and deployment package plan."),
    ("lab_test", "Lab test", "Deploy to the test collection and capture installation and application evidence."),
    ("change", "Change creation", "Create the governed change with impact, schedule, rollback and evidence."),
    ("notify", "Stakeholder schedule", "Notify application and infrastructure owners of dates and responsibilities."),
    ("approval", "Approval gate", "An authorized approver confirms the KBs, collections and deployment schedule."),
    ("preflight", "One-day preflight", "Check client health, content, disk capacity, maintenance windows and reachability."),
    ("deploy", "Phased deployment", "Run test, pilot and production waves using approved SCCM collections."),
    ("compliance", "Live compliance", "Track compliant, pending, in-progress, failed, restart-pending and unknown devices."),
    ("validation", "Application validation", "Request and record post-patch service and business validation."),
    ("close", "Close and report", "Publish final compliance evidence and close the change."),
]
_EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

def _org(value):
    value = str(value or config.DEFAULT_ORGANIZATION_ID or "").strip()
    if not value: raise ValueError("organization_id is required")
    return value


def _dicts(cursor):
    names = [item.name for item in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def _event(connection, organization_id, cycle_id, stage, status, actor, details=None):
    code = STAGES[stage][0]
    with connection.cursor() as cursor:
        cursor.execute("""INSERT INTO ops_agent.sccm_patch_events
            (organization_id,cycle_id,stage,stage_code,status,actor,details) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)""",
            (organization_id,cycle_id, stage, code, status, actor, json.dumps(details or {})))


def create(values, actor, organization_id=None):
    organization_id = _org(organization_id)
    database.initialize()
    required = ["name", "release_date", "test_date", "production_date", "deadline_date",
                "software_update_group", "deployment_package", "test_collection",
                "production_collection", "change_system"]
    missing = [name for name in required if not str(values.get(name) or "").strip()]
    if missing:
        raise ValueError("Missing required fields: " + ", ".join(missing))
    test = datetime.fromisoformat(str(values["test_date"]).replace("Z", "+00:00"))
    production = datetime.fromisoformat(str(values["production_date"]).replace("Z", "+00:00"))
    deadline = datetime.fromisoformat(str(values["deadline_date"]).replace("Z", "+00:00"))
    if not test < production <= deadline:
        raise ValueError("Dates must follow: test < production <= deadline")
    stakeholders = list(dict.fromkeys(values.get("stakeholder_emails") or []))
    applications = list(dict.fromkeys(values.get("application_emails") or []))
    invalid = [email for email in stakeholders + applications if not _EMAIL.fullmatch(str(email))]
    if invalid:
        raise ValueError("Invalid email address: " + ", ".join(invalid))
    cycle_id = f"PATCH-{uuid4().hex[:10].upper()}"
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""INSERT INTO ops_agent.sccm_patch_cycles
                (organization_id,cycle_id,name,status,current_stage,release_date,test_date,production_date,deadline_date,
                 kb_ids,software_update_group,deployment_package,test_collection,pilot_collection,
                 production_collection,change_system,change_id,stakeholder_emails,application_emails,created_by)
                VALUES (%s,%s,%s,'active',0,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (organization_id,cycle_id, values["name"], values["release_date"], test, production, deadline,
                 values.get("kb_ids") or [], values["software_update_group"], values["deployment_package"],
                 values["test_collection"], values.get("pilot_collection") or None,
                 values["production_collection"], values["change_system"], values.get("change_id") or None,
                 stakeholders, applications, actor))
        _event(connection, organization_id, cycle_id, 0, "in_progress", actor, {"kb_ids": values.get("kb_ids") or []})
        connection.commit()
    ops_log.write("sccm_patch", "INFO", "cycle_created", json.dumps({"cycle_id": cycle_id, "actor": actor}), cycle_id, organization_id)
    return get(cycle_id, organization_id)


def list_cycles(organization_id=None):
    organization_id = _org(organization_id)
    database.initialize()
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM ops_agent.sccm_patch_cycles WHERE organization_id=%s ORDER BY created_at DESC", (organization_id,))
            rows = _dicts(cursor)
    for row in rows:
        row["stage"] = stage_view(row)
    return rows


def get(cycle_id, organization_id=None):
    organization_id = _org(organization_id)
    database.initialize()
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM ops_agent.sccm_patch_cycles WHERE organization_id=%s AND cycle_id=%s", (organization_id,cycle_id))
            rows = _dicts(cursor)
            if not rows:
                raise KeyError(cycle_id)
            cursor.execute("SELECT * FROM ops_agent.sccm_patch_events WHERE organization_id=%s AND cycle_id=%s ORDER BY occurred_at", (organization_id,cycle_id))
            events = _dicts(cursor)
    cycle = rows[0]
    cycle["stage"] = stage_view(cycle)
    cycle["events"] = events
    cycle["stages"] = [{"index": i, "code": code, "title": title, "description": description,
                         "state": "complete" if i < cycle["current_stage"] else "active" if i == cycle["current_stage"] else "pending"}
                        for i, (code, title, description) in enumerate(STAGES)]
    return cycle


def stage_view(cycle):
    index = min(max(int(cycle.get("current_stage", 0)), 0), len(STAGES) - 1)
    code, title, description = STAGES[index]
    return {"index": index, "code": code, "title": title, "description": description}


def advance(cycle_id, actor, evidence=None, organization_id=None):
    organization_id = _org(organization_id); cycle = get(cycle_id, organization_id)
    current = int(cycle["current_stage"])
    if current == 5 and cycle["approval_status"] != "approved":
        raise PermissionError("Patch cycle requires approval before preflight and deployment")
    if current >= len(STAGES) - 1:
        return cycle
    target = current + 1
    status = "completed" if target == len(STAGES) - 1 else "active"
    with database.connect() as connection:
        _event(connection, organization_id, cycle_id, current, "completed", actor, evidence or {})
        _event(connection, organization_id, cycle_id, target, "in_progress", actor, {})
        with connection.cursor() as cursor:
            cursor.execute("UPDATE ops_agent.sccm_patch_cycles SET current_stage=%s,status=%s,updated_at=NOW() WHERE organization_id=%s AND cycle_id=%s",
                           (target, status, organization_id,cycle_id))
        connection.commit()
    ops_log.write("sccm_patch", "INFO", "stage_advanced", json.dumps({"cycle_id": cycle_id, "from": current, "to": target, "actor": actor}), cycle_id, organization_id)
    updated = get(cycle_id, organization_id)
    notification = _notify_for_stage(updated, target)
    if notification:
        with database.connect() as connection:
            _event(connection, organization_id, cycle_id, target, "notification", "opsagent", notification)
            connection.commit()
    return get(cycle_id, organization_id)


def _notify_for_stage(cycle, stage):
    recipients, subject, body = [], "", ""
    if stage == 4:
        recipients = cycle.get("stakeholder_emails") or []
        subject = f"[{cycle['cycle_id']}] Patch schedule: {cycle['name']}"
        body = (f"OpsAgent One scheduled the SCCM patch cycle {cycle['name']}.\n\n"
                f"KBs: {', '.join(cycle.get('kb_ids') or []) or 'See change record'}\n"
                f"Test: {cycle['test_date']}\nProduction: {cycle['production_date']}\n"
                f"Deadline: {cycle['deadline_date']}\nChange: {cycle.get('change_id') or 'Pending'}\n\n"
                "Deployment remains approval-gated. Please review impact and availability.")
    elif stage == 9:
        recipients = cycle.get("application_emails") or []
        subject = f"[{cycle['cycle_id']}] Post-patch application validation required"
        body = (f"Patching reached application validation for {cycle['name']}.\n\n"
                "Please validate services, databases, URLs, integrations and critical business functions, "
                "then return the evidence to the change record.")
    elif stage == 10:
        recipients = list(dict.fromkeys((cycle.get("stakeholder_emails") or []) + (cycle.get("application_emails") or [])))
        subject = f"[{cycle['cycle_id']}] Patch cycle completed: {cycle['name']}"
        body = (f"OpsAgent One completed the governed SCCM patch cycle {cycle['name']}.\n\n"
                f"Change: {cycle.get('change_id') or 'Not supplied'}\n"
                "Review SCCM compliance and OpsAgent audit evidence before closing the enterprise change.")
    if not subject:
        return None
    result = email_handler.send_patch_pipeline_email(recipients, subject, body, cycle["cycle_id"])
    return {"subject": subject, **result}


def approve(cycle_id, actor, organization_id=None):
    organization_id = _org(organization_id); cycle = get(cycle_id, organization_id)
    if int(cycle["current_stage"]) < 5:
        raise ValueError("Advance the cycle to the Approval gate before approving")
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""UPDATE ops_agent.sccm_patch_cycles SET approval_status='approved',
                approved_by=%s,approved_at=NOW(),updated_at=NOW() WHERE organization_id=%s AND cycle_id=%s""", (actor,organization_id,cycle_id))
        _event(connection, organization_id,cycle_id, 5, "approved", actor, {})
        connection.commit()
    ops_log.write("sccm_patch", "INFO", "cycle_approved", json.dumps({"cycle_id": cycle_id, "approver": actor}), cycle_id, organization_id)
    return get(cycle_id, organization_id)


def compliance(cycle_id, organization_id=None):
    cycle = get(cycle_id, organization_id)
    inventory = sccm_operations.inventory(force=True)
    deployments = inventory.get("deployments", [])
    relevant = [row for row in deployments if str(row.get("CollectionName") or "") in {
        cycle.get("test_collection"), cycle.get("pilot_collection"), cycle.get("production_collection")
    }]
    result = {"compliant": 0, "in_progress": 0, "failed": 0, "pending": 0, "unknown": 0}
    for row in relevant:
        result["compliant"] += int(row.get("NumberSuccess") or 0)
        result["in_progress"] += int(row.get("NumberInProgress") or 0)
        result["failed"] += int(row.get("NumberErrors") or 0)
        result["unknown"] += int(row.get("NumberOther") or 0)
    managed = int((inventory.get("summary") or {}).get("devices") or 0)
    result["pending"] = max(0, managed - sum(result.values()))
    return {"cycle_id": cycle_id, "collected_at": inventory.get("collected_at"), "counts": result, "deployments": relevant}

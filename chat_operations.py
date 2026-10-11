"""Persisted, approval-gated infrastructure operations initiated from web chat."""
from datetime import datetime, timedelta, timezone
import re
import secrets

import database
import ops_log
import slack_actions
from providers import aws


def parse_approval(text):
    match = re.fullmatch(r"\s*APPROVE\s+(CHAT-[0-9A-F]{8})\s*", text or "", re.I)
    return match.group(1).upper() if match else None


def is_operation(text):
    return slack_actions.parse_action_request(text) is not None


def _action_label(action):
    return {
        "start_instance": "Start", "stop_instance": "Stop",
        "reboot_instance": "Reboot", "create_snapshot": "Create snapshot",
        "delete_snapshot": "Delete snapshot", "delete_volume": "Delete volume",
    }.get(action, action.replace("_", " ").title())


def request_operation(text, session_id, requester):
    parsed = slack_actions.parse_action_request(text)
    if not parsed:
        return "I could not identify the requested operation. Include an action and exact server name, IP address, or AWS resource ID."
    if parsed.get("error") == "target_not_found":
        return "I recognized an infrastructure operation, but could not match its target in the live inventory. Check the server name, IP address, or instance ID."
    if parsed.get("error"):
        return f"I cannot prepare this operation: {parsed['error'].replace('_', ' ')}."

    request_id = f"CHAT-{secrets.token_hex(4).upper()}"
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=15)
    database.initialize()
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""INSERT INTO ops_agent.chat_action_requests
                (request_id,session_id,status,requester,action,server_name,provider,
                 resource_id,region,created_at,expires_at)
                VALUES (%s,%s,'pending',%s,%s,%s,%s,%s,%s,%s,%s)""", (
                request_id, session_id, requester, parsed["action"],
                parsed["server_name"], parsed["provider"], parsed["resource_id"],
                parsed.get("region"), now, expires,
            ))
        connection.commit()
    ops_log.write("chat", "INFO", "operation_requested", request_id, request_id)
    label = _action_label(parsed["action"])
    approval_instruction = ("Use the MFA termination approval card below. Do not place authenticator codes in chat." if parsed["action"] == "terminate_instance" else f"To authorize this exact change, reply: APPROVE {request_id}")
    return (
        f"REQUEST ACKNOWLEDGED — no infrastructure change has run\n\n"
        f"Request ID: {request_id}\n"
        f"Action: {label}\n"
        f"Target: {parsed['server_name']}\n"
        f"Resource: {parsed['resource_id']}\n"
        f"Region: {parsed.get('region') or 'default'}\n"
        f"Expires: 15 minutes\n\n" + approval_instruction
    )


def _load(cursor, request_id, session_id):
    cursor.execute("""SELECT status,requester,action,server_name,provider,resource_id,
        region,expires_at FROM ops_agent.chat_action_requests
        WHERE request_id=%s AND session_id=%s FOR UPDATE""", (request_id, session_id))
    row = cursor.fetchone()
    if not row:
        return None
    keys = ("status", "requester", "action", "server_name", "provider", "resource_id", "region", "expires_at")
    return dict(zip(keys, row))


def approve(request_id, session_id, user, authorized):
    database.initialize()
    with database.connect() as connection:
        with connection.cursor() as cursor:
            item = _load(cursor, request_id, session_id)
            if not item:
                return "Approval request not found in this conversation."
            if item["status"] != "pending":
                return f"Request {request_id} is already {item['status']}."
            if item["expires_at"] < datetime.now(timezone.utc):
                cursor.execute("UPDATE ops_agent.chat_action_requests SET status='expired',updated_at=NOW() WHERE request_id=%s", (request_id,))
                connection.commit()
                return f"Request {request_id} expired. Submit the operation again to create a new approval."
            if not authorized(item["action"], user):
                return "Your current role cannot approve this infrastructure operation. Ask an authorized Operator or Admin."
            if item["action"] == "terminate_instance":
                return f"MFA_REQUIRED {request_id}"
            cursor.execute("""UPDATE ops_agent.chat_action_requests SET status='executing',approver=%s,
                approved_at=NOW(),updated_at=NOW() WHERE request_id=%s""", (user["username"], request_id))
        connection.commit()

    before = "unknown"
    try:
        before = str(aws.describe_instance(item["resource_id"], item["region"]).get("state") or "unknown")
        result = aws.execute(
            item["action"], item["resource_id"], approved=True,
            actor=f"enterprise-chat:{user['username']}", requester=item["requester"],
            approver=user["username"], source="enterprise_chat", region=item["region"],
            request_id=request_id,
        )
        success = bool(result.get("success"))
        after = str(result.get("after_status") or result.get("state") or "requested")
        error = result.get("error")
        verified = bool(result.get("dry_run"))
        if success and not result.get("dry_run") and item["action"] in {"start_instance", "stop_instance"}:
            expected = "running" if item["action"] == "start_instance" else "stopped"
            verification = aws.wait_for_instance_state(
                item["resource_id"], expected, region=item["region"],
                timeout=120, poll_seconds=5,
            )
            verified = bool(verification.get("verified"))
            after = str((verification.get("instance") or {}).get("state") or after)
            error = error or verification.get("error")
        elif success and not result.get("dry_run"):
            verified = True
    except Exception as exc:
        success, verified, after, error = False, False, "unknown", f"{type(exc).__name__}: {exc}"

    status = "completed" if success and verified else ("verification_pending" if success else "failed")
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""UPDATE ops_agent.chat_action_requests SET status=%s,executed_at=NOW(),
                before_state=%s,after_state=%s,success=%s,error_message=%s,updated_at=NOW()
                WHERE request_id=%s""", (status, before, after, success, error, request_id))
        connection.commit()
    ops_log.write("chat", "INFO" if success else "ERROR", f"operation_{status}", request_id, request_id)
    if not success:
        return f"OPERATION FAILED\n\nRequest ID: {request_id}\nTarget: {item['server_name']}\nError: {error or 'Unknown provider error'}"
    if not verified:
        return (
            f"OPERATION ACCEPTED — final state not yet verified\n\nRequest ID: {request_id}\n"
            f"Action: {_action_label(item['action'])}\nTarget: {item['server_name']}\n"
            f"State: {before} → {after}\nAWS accepted the change, but verification timed out. "
            f"Refresh inventory or ask me to check the server state."
        )
    return (
        f"OPERATION COMPLETED\n\nRequest ID: {request_id}\n"
        f"Action: {_action_label(item['action'])}\nTarget: {item['server_name']}\n"
        f"State: {before} → {after}\nApproval: {user['username']}\nAudit: Recorded"
    )


def approve_termination(request_id, session_id, user, authorized):
    """Execute termination only after the API independently verifies Admin MFA."""
    database.initialize()
    with database.connect() as connection:
        with connection.cursor() as cursor:
            item = _load(cursor, request_id, session_id)
            if not item:
                return {"success": False, "message": "Approval request not found in this conversation."}
            if item["action"] != "terminate_instance" or item["status"] != "pending":
                return {"success": False, "message": "This is not a pending termination request."}
            if item["expires_at"] < datetime.now(timezone.utc):
                return {"success": False, "message": "The termination request expired."}
            if user.get("role") != "Admin" or not authorized("terminate_instance", user):
                return {"success": False, "message": "Admin authorization is required."}
            cursor.execute("UPDATE ops_agent.chat_action_requests SET status='executing',approver=%s,approved_at=NOW(),updated_at=NOW() WHERE request_id=%s", (user["username"], request_id))
        connection.commit()
    before = str(aws.describe_instance(item["resource_id"], item["region"]).get("state") or "unknown")
    protection = aws.termination_protection(item["resource_id"], item["region"])
    if protection:
        return {"success": False, "message": "AWS termination protection is enabled. Disable it through a separate approved change first."}
    result = aws.execute("terminate_instance", item["resource_id"], approved=True, actor=f"enterprise-chat:{user['username']}", requester=item["requester"], approver=user["username"], source="enterprise_chat_mfa", region=item["region"], request_id=request_id)
    success = bool(result.get("success"))
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("UPDATE ops_agent.chat_action_requests SET status=%s,executed_at=NOW(),before_state=%s,after_state=%s,success=%s,error_message=%s,updated_at=NOW() WHERE request_id=%s", ("completed" if success else "failed", before, result.get("after_status") or "unknown", success, result.get("error"), request_id))
        connection.commit()
    return {"success": success, "request_id": request_id, "instance_id": item["resource_id"], "before": before, "after": result.get("after_status"), "message": result.get("message") or result.get("error") or ("Termination accepted" if success else "Termination failed")}

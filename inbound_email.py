"""Inbound IMAP requests with mandatory email approval before AWS execution."""

import email
import imaplib
import json
import re
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import parseaddr, parsedate_to_datetime

from providers import aws as aws_operations
import config
import email_handler
import email_metrics
import health_status
import server_inventory
import ops_log
import database

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

try:
    import psycopg
except ImportError:
    psycopg = None

_LOCK = threading.RLock()
_ACTIONS = set(aws_operations.MUTATING_ACTIONS)


def _ensure_postgresql_table(connection):
    import database
    database.initialize()


def _load_postgresql():
    if psycopg is None or not config.DATABASE_URL:
        raise RuntimeError("PostgreSQL storage requires psycopg and DATABASE_URL")
    with psycopg.connect(config.DATABASE_URL, connect_timeout=5) as connection:
        _ensure_postgresql_table(connection)
        with connection.cursor() as cursor:
            cursor.execute("""SELECT request_id,status,requester,approver,action,target_identifier,
                alert_date,server_name,ip_address,original_subject,root_message_id,created_at,expires_at,
                approved_at,executed_at,instance_type,volume_id,size_gib,network_interface_id,
                before_state,after_state,success,verified,dry_run,error_message,snapshot_id,description
                FROM ops_agent.email_action_requests ORDER BY created_at""")
            records = []
            for row in cursor.fetchall():
                params = {key: value for key, value in {
                    "instance_type": row[15], "volume_id": row[16], "size_gib": row[17],
                    "network_interface_id": row[18],
                    "snapshot_id": row[25], "description": row[26],
                }.items() if value is not None}
                item = {"request_id":row[0],"status":row[1],"requester":row[2],"approver":row[3],
                    "action":row[4],"identifier":row[5],"alert_date":row[6],"server_name":row[7],
                    "ip_address":row[8],"original_subject":row[9] or "","root_message_id":row[10] or "",
                    "created_at":row[11].isoformat(),"expires_at":row[12].isoformat() if row[12] else None,
                    "approved_at":row[13].isoformat() if row[13] else None,
                    "executed_at":row[14].isoformat() if row[14] else None,"params":params,
                    "before_state":{"state":row[19]} if row[19] else {},
                    "after_state":{"state":row[20]} if row[20] else {},
                    "result":{"success":row[21],"dry_run":row[23],"error":row[24]},
                    "verification":{"verified":row[22]},}
                records.append(item)
        connection.commit()
    return {"pending": {row["request_id"]: row for row in records}, "processed_messages": []}


def _load():
    return _load_postgresql()


def _save_postgresql(state):
    if psycopg is None or not config.DATABASE_URL:
        raise RuntimeError("PostgreSQL storage requires psycopg and DATABASE_URL")
    with psycopg.connect(config.DATABASE_URL, connect_timeout=5) as connection:
        _ensure_postgresql_table(connection)
        with connection.cursor() as cursor:
            for item in state.get("pending", {}).values():
                params = item.get("params") or {}
                before = item.get("before_state") or {}
                after = item.get("after_state") or {}
                result = item.get("result") or {}
                verification = item.get("verification") or {}
                cursor.execute("""INSERT INTO ops_agent.email_action_requests
                    (request_id,status,requester,approver,action,target_identifier,alert_date,
                    server_name,ip_address,original_subject,root_message_id,expires_at,approved_at,executed_at,
                    instance_type,volume_id,size_gib,network_interface_id,before_state,after_state,
                    success,verified,dry_run,error_message,snapshot_id,description)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (request_id) DO UPDATE SET status=EXCLUDED.status,approver=EXCLUDED.approver,
                    approved_at=EXCLUDED.approved_at,executed_at=EXCLUDED.executed_at,
                    before_state=EXCLUDED.before_state,after_state=EXCLUDED.after_state,
                    success=EXCLUDED.success,verified=EXCLUDED.verified,dry_run=EXCLUDED.dry_run,
                    error_message=EXCLUDED.error_message,snapshot_id=EXCLUDED.snapshot_id,
                    description=EXCLUDED.description,updated_at=NOW()""", (
                    item["request_id"],item.get("status","unknown"),item.get("requester","unknown"),
                    item.get("approver"),item.get("action","unknown"),item.get("identifier","unknown"),
                    item.get("alert_date"),item.get("server_name"),item.get("ip_address"),
                    item.get("original_subject"),item.get("root_message_id"),item.get("expires_at"),
                    item.get("approved_at"),item.get("executed_at"),params.get("instance_type"),
                    params.get("volume_id"),params.get("size_gib"),params.get("network_interface_id"),
                    before.get("state"),after.get("state"),result.get("success"),verification.get("verified"),
                    result.get("dry_run"),result.get("error") or verification.get("error"),
                    params.get("snapshot_id"),params.get("description"),
                ))
        connection.commit()


def _save(state):
    _save_postgresql(state)


def request_history():
    """Return persisted email requests newest first for dashboard/audit display."""
    with _LOCK:
        rows = list(_load().get("pending", {}).values())
    return sorted(rows, key=lambda row: row.get("created_at", ""), reverse=True)


def _body(message):
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_type() == "text/plain" and "attachment" not in str(part.get("Content-Disposition", "")):
                return part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="replace")
        return ""
    return message.get_payload(decode=True).decode(message.get_content_charset() or "utf-8", errors="replace")


def parse_request(text):
    """Parse: AWS REQUEST <action> <exact-resource-id> [key=value ...]."""
    match = re.search(r"(?im)^\s*AWS\s+REQUEST\s+([a-z_]+)\s+((?:i|snap|vol)-[0-9a-f]{8,17})(.*)$", text or "")
    if not match or match.group(1) not in _ACTIONS:
        return None
    action, identifier = match.group(1), match.group(2).lower()
    if action == "delete_snapshot" and not identifier.startswith("snap-"):
        return None
    if action == "delete_volume" and not identifier.startswith("vol-"):
        return None
    if action not in {"delete_snapshot", "delete_volume"} and not identifier.startswith("i-"):
        return None
    params = dict(re.findall(r"\b(instance_type|volume_id|size_gib|network_interface_id|description)=([^\s]+)", match.group(3)))
    if action == "delete_snapshot":
        params["snapshot_id"] = identifier
    if action == "delete_volume":
        params["volume_id"] = identifier
    if "size_gib" in params:
        try:
            params["size_gib"] = int(params["size_gib"])
        except ValueError:
            return None
    return {"action": action, "identifier": identifier, "params": params}


_NATURAL_ACTIONS = (
    ("delete_volume", r"(?im)^\s*(?:(?:please|kindly)\s+)?(?:delete|remove)\s+(?:an?\s+)?(?:ebs\s+)?(?:volume|drive|disk)\b"),
    ("delete_snapshot", r"(?im)^\s*(?:(?:please|kindly)\s+)?(?:delete|remove)\s+(?:an?\s+)?snapshot\b"),
    ("create_snapshot", r"(?im)^\s*(?:(?:please|kindly)\s+)?(?:create|take)\s+(?:an?\s+)?snapshot\b"),
    ("reboot_instance", r"(?im)^\s*(?:(?:please|kindly)\s+|(?:can|could|would)\s+you\s+|i\s+(?:want|need)\s+(?:you\s+)?to\s+|need\s+to\s+)?(?:reboot|restart)\b"),
    ("start_instance", r"(?im)^\s*(?:(?:please|kindly)\s+|(?:can|could|would)\s+you\s+|i\s+(?:want|need)\s+(?:you\s+)?to\s+|need\s+to\s+)?(?:start|power\s+on|turn\s+on|boot\s+up)\b"),
    ("stop_instance", r"(?im)^\s*(?:(?:please|kindly)\s+|(?:can|could|would)\s+you\s+|i\s+(?:want|need)\s+(?:you\s+)?to\s+|need\s+to\s+)?(?:stop|power\s+off|turn\s+off|shut\s*down)\b"),
)


def _resolve_inventory_target(text):
    records = server_inventory.load()
    instance_match = re.search(r"\bi-[0-9a-f]{8,17}\b", text, re.I)
    if instance_match:
        matches = [row for row in records if row.get("aws_instance_id", "").lower() == instance_match.group().lower()]
        return (matches[0], []) if len(matches) == 1 else (None, matches)
    for row in records:
        identities = [row.get("server_name"), row.get("ip_address"), row.get("public_ip_address"), row.get("private_ip_address")]
        if any(value and re.search(rf"(?<![\w.-]){re.escape(value)}(?![\w.-])", text, re.I) for value in identities):
            return row, []
    matches = server_inventory.search(text, limit=5)
    return (matches[0], []) if len(matches) == 1 else (None, matches)


def parse_natural_request(text):
    lowered = (text or "").lower()
    action = next((name for name, pattern in _NATURAL_ACTIONS if re.search(pattern, lowered)), None)
    if not action:
        return None, []
    if action == "delete_snapshot":
        snapshot = re.search(r"\bsnap-[0-9a-f]{8,17}\b", text or "", re.I)
        if not snapshot:
            return {"action": action, "needs_snapshot_id": True}, []
        snapshot_id = snapshot.group().lower()
        return {"action": action, "identifier": snapshot_id,
                "params": {"snapshot_id": snapshot_id},
                "server_name": "EBS Snapshot", "ip_address": ""}, []
    if action == "delete_volume":
        volume = re.search(r"\bvol-[0-9a-f]{8,17}\b", text or "", re.I)
        if not volume:
            return {"action": action, "needs_volume_id": True}, []
        volume_id = volume.group().lower()
        return {"action": action, "identifier": volume_id,
                "params": {"volume_id": volume_id},
                "server_name": "EBS Volume", "ip_address": ""}, []
    record, candidates = _resolve_inventory_target(text)
    if not record:
        return {"action": action, "needs_target": True}, candidates
    if record.get("vm_type") != "aws" or not record.get("aws_instance_id"):
        return {"action": action, "unsupported_record": record}, []
    request = {
        "action": action, "identifier": record["aws_instance_id"], "params": {},
        "server_name": record["server_name"], "ip_address": record["ip_address"],
    }
    if action == "create_snapshot":
        volume = re.search(r"\bvol-[0-9a-f]{8,17}\b", text or "", re.I)
        if volume:
            request["params"]["volume_id"] = volume.group().lower()
        request["params"]["description"] = f"OpsAgent email snapshot for {record['server_name']}"
    return request, []


def _inventory_summary():
    return "\n".join(
        f"- {row['server_name']} | {row['vm_type']} | {row['os_type']} | "
        f"SSH {row['ip_address']} | instance {row.get('aws_instance_id') or 'N/A'} | {row['status']}"
        for row in server_inventory.load()
    ) or "No enabled inventory records are available."


def _answer_read_only(sender, message, text):
    lowered = text.lower()
    if re.search(r"\b(?:list|show|what|which)\b.*\b(?:servers?|vms?|inventory)\b", lowered):
        answer = "Enabled infrastructure inventory:\n\n" + _inventory_summary()
    elif re.search(r"\b(?:status|state|running|stopped|online|offline)\b", lowered):
        record, candidates = _resolve_inventory_target(text)
        if record and record.get("vm_type") == "aws" and record.get("aws_instance_id"):
            try:
                state = aws_operations.describe_instance(record["aws_instance_id"], record.get("aws_region") or config.AWS_REGION)
                answer = f"{record['server_name']} AWS status:\n\n" + json.dumps(state, indent=2, default=str)
            except Exception as exc:
                answer = f"I found {record['server_name']}, but AWS status lookup failed: {exc}"
        else:
            names = ", ".join(row["server_name"] for row in candidates) or "none"
            answer = f"I could not identify one exact server. Matching candidates: {names}. Reply with the server name or IP."
    elif OpenAI and config.OPENAI_API_KEY:
        client = OpenAI(api_key=config.OPENAI_API_KEY)
        response = client.chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": (
                    "You are A2Z OpsAgent. Answer the authorized operator's read-only infrastructure question "
                    "about AWS, Windows, Linux, or VMware concisely. Do not claim to execute actions. If a target "
                    "is ambiguous, ask for its exact server name or IP. Inventory:\n" + _inventory_summary()
                )},
                {"role": "user", "content": text[:4000]},
            ],
            temperature=0,
        )
        answer = response.choices[0].message.content
    else:
        answer = "I can answer server inventory/status questions or process start, stop, and reboot requests. Include a server name, IP, or instance ID."
    _send(sender, message.get("Subject", "OpsAgent response"), answer, message.get("Message-ID"))


def _send(to, subject, body, in_reply_to=None, references=None, cc=None):
    message = EmailMessage()
    message["From"] = config.SMTP_FROM_EMAIL
    message["To"] = to
    if cc:
        message["Cc"] = ", ".join(cc) if isinstance(cc, (set, list, tuple)) else cc
    message["Subject"] = subject
    if in_reply_to:
        message["In-Reply-To"] = in_reply_to
        message["References"] = references or in_reply_to
    message.set_content(body)
    return email_handler._send(message)


def _new_request(sender, message, request):
    if sender not in config.EMAIL_REQUEST_SENDERS:
        return None
    request_id = f"OPS-{secrets.token_hex(4).upper()}"
    now = datetime.now(timezone.utc)
    item = {
        **request, "request_id": request_id, "requester": sender,
        "alert_date": message.get("Date") or now.isoformat(),
        "original_subject": message.get("Subject", ""),
        "root_message_id": message.get("Message-ID", ""),
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=config.EMAIL_APPROVAL_EXPIRY_MINUTES)).isoformat(),
        "status": "pending",
    }
    with _LOCK:
        state = _load()
        state["pending"][request_id] = item
        _save(state)
    details = " ".join(f"{k}={v}" for k, v in request["params"].items()) or "none"
    # Gmail requires a stable subject plus References/In-Reply-To headers to
    # reliably keep the request, acknowledgement, approval, and result together.
    thread_subject = message.get("Subject", "").strip() or f"OpsAgent request {request_id}"
    destructive_warning = (
        "\nWARNING: EBS volume deletion is permanent. The volume must be detached, available, "
        "explicitly tagged for deletion, and should have a recovery snapshot.\n"
        if request["action"] == "delete_volume" else ""
    )
    _send(
        sender, thread_subject,
        f"REQUEST ACKNOWLEDGED — no AWS action has run.\n\n"
        f"Alert date: {item['alert_date']}\nRequester: {sender}\nAction: {request['action']}\n"
        f"Target: {request['identifier']}\nParameters: {details}\nRequest ID: {request_id}\n"
        f"{destructive_warning}"
        f"Approval expiry: {item['expires_at']}\n\n"
        f"Authorized approver: reply-all in this thread with exactly:\nAPPROVE {request_id}",
        message.get("Message-ID"), cc=config.EMAIL_APPROVERS,
    )
    return request_id


def _describe_before_action(item):
    params = item.get("params") or {}
    if item["action"] == "delete_volume":
        return aws_operations.describe_volume(
            params.get("volume_id") or item["identifier"], config.AWS_REGION
        )
    if item["action"] == "delete_snapshot":
        return aws_operations.describe_snapshot(
            params.get("snapshot_id") or item["identifier"], config.AWS_REGION
        )
    if item["action"] == "create_snapshot" and params.get("volume_id"):
        return aws_operations.describe_volume(params["volume_id"], config.AWS_REGION)
    return aws_operations.describe_instance(item["identifier"], config.AWS_REGION)


def _verify_action(item, result):
    if not result.get("success"):
        return {"verified": False, "error": result.get("error")}
    if result.get("dry_run"):
        return {"verified": True, "instance": item.get("before_state") or {}}
    if item["action"] in {"start_instance", "stop_instance"}:
        expected = "running" if item["action"] == "start_instance" else "stopped"
        return aws_operations.wait_for_instance_state(
            item["identifier"], expected, config.AWS_REGION,
            timeout=config.EMAIL_AWS_VERIFY_SECONDS,
        )
    if item["action"] == "create_snapshot":
        snapshot_id = result.get("snapshot_id")
        if not snapshot_id:
            return {"verified": False, "error": "AWS did not return a snapshot ID"}
        snapshot = aws_operations.describe_snapshot(snapshot_id, config.AWS_REGION)
        return {"verified": snapshot.get("state") in {"pending", "completed"},
                "instance": snapshot}
    if item["action"] == "delete_snapshot":
        verification = aws_operations.wait_for_snapshot_deleted(
            result.get("snapshot_id") or item["identifier"], config.AWS_REGION,
            timeout=config.EMAIL_AWS_VERIFY_SECONDS,
        )
        verification["instance"] = {"state": verification.get("state", "unknown")}
        return verification
    if item["action"] == "delete_volume":
        verification = aws_operations.wait_for_volume_deleted(
            result.get("volume_id") or item["identifier"], config.AWS_REGION,
            timeout=config.EMAIL_AWS_VERIFY_SECONDS,
        )
        verification["instance"] = {"state": verification.get("state", "unknown")}
        return verification
    try:
        return {"verified": True,
                "instance": aws_operations.describe_instance(item["identifier"], config.AWS_REGION)}
    except Exception as exc:
        return {"verified": False, "error": str(exc)}


def _approval(sender, request_id, message):
    if sender not in config.EMAIL_APPROVERS:
        return
    with _LOCK:
        state = _load()
        item = state["pending"].get(request_id)
        if not item or item.get("status") != "pending":
            return
        if datetime.now(timezone.utc) > datetime.fromisoformat(item["expires_at"]):
            item["status"] = "expired"
            _save(state)
            _send(sender, f"[EXPIRED][{request_id}]", "Approval was not executed because the request expired.", message.get("Message-ID"))
            return
        # Mark executing before the API call to prevent duplicate approvals.
        item["status"] = "executing"
        item["approver"] = sender
        item["approved_at"] = datetime.now(timezone.utc).isoformat()
        try:
            item["before_state"] = _describe_before_action(item)
        except Exception as exc:
            item["before_state"] = {"error": str(exc)}
        _save(state)
    result = aws_operations.execute(
        item["action"], item["identifier"], approved=True,
        actor=f"email:{sender}", region=config.AWS_REGION,
        request_id=request_id, source="gmail", requester=item.get("requester"), approver=sender,
        **item.get("params", {}),
    )
    verification = _verify_action(item, result)
    with _LOCK:
        state = _load()
        saved = state["pending"][request_id]
        saved["status"] = "completed" if result.get("success") and verification.get("verified") else "failed"
        saved["executed_at"] = datetime.now(timezone.utc).isoformat()
        saved["result"] = result
        saved["verification"] = verification
        saved["after_state"] = verification.get("instance")
        _save(state)
    before = item.get("before_state", {}).get("state", "unknown")
    after = (verification.get("instance") or {}).get("state", "unknown")
    summary = (
        f"AWS REQUEST RESULT\n\nRequest ID: {request_id}\nRequester: {item['requester']}\n"
        f"Approver: {sender}\nAction: {item['action']}\nTarget: {item['identifier']}\n"
        f"Approved at: {item['approved_at']}\nExecuted at: {saved['executed_at']}\n"
        f"Before state: {before}\nAfter state: {after}\nVerified: {verification.get('verified')}\n"
        f"Dry run: {result.get('dry_run')}\nSuccess: {result.get('success')}\n"
        f"Volume ID: {result.get('volume_id') or (item.get('params') or {}).get('volume_id') or 'N/A'}\n"
        f"Snapshot ID: {result.get('snapshot_id') or (item.get('params') or {}).get('snapshot_id') or 'N/A'}\n"
        f"Error: {result.get('error') or verification.get('error') or 'none'}"
    )
    _send(
        item["requester"], item.get("original_subject") or f"OpsAgent request {request_id}", summary,
        message.get("Message-ID"),
        references=" ".join(filter(None, (item.get("root_message_id"), message.get("Message-ID")))),
        cc=config.EMAIL_APPROVERS,
    )


def process_message(message):
    sender = parseaddr(message.get("From", ""))[1].lower()
    message_id = message.get("Message-ID", "")
    subject = message.get("Subject", "")
    ops_log.write("gmail", "INFO", "message_received",
                  f"Sender={sender}; subject={subject[:160]!r}", message_id)
    email_metrics.record("received", message_id=message_id, sender=sender, subject=subject)
    text = f"{message.get('Subject', '')}\n{_body(message)}"
    approval = re.search(r"(?im)^\s*APPROVE\s+(OPS-[0-9A-F]{8})\s*$", text)
    if approval:
        ops_log.write("gmail", "INFO", "approval_detected", approval.group(1), message_id)
        _approval(sender, approval.group(1), message)
        email_metrics.record("processed", message_id=message_id, sender=sender, subject=subject,
                             request_id=approval.group(1), details="Approval message processed")
        return
    request = parse_request(text)
    if request:
        request_id = _new_request(sender, message, request)
        if request_id:
            ops_log.write("gmail", "INFO", "request_acknowledged", request_id, message_id)
            email_metrics.record("acknowledged", message_id=message_id, sender=sender, subject=subject,
                                 request_id=request_id, details="Request acknowledgement sent")
        else:
            ops_log.write("gmail", "WARNING", "message_ignored",
                          "Sender is not in EMAIL_REQUEST_SENDERS", message_id)
            email_metrics.record("ignored", message_id=message_id, sender=sender, subject=subject,
                                 details="Sender is not in EMAIL_REQUEST_SENDERS")
        return
    if sender not in config.EMAIL_REQUEST_SENDERS:
        ops_log.write("gmail", "WARNING", "message_ignored",
                      f"Sender {sender} is not in EMAIL_REQUEST_SENDERS", message_id)
        email_metrics.record("ignored", message_id=message_id, sender=sender, subject=subject,
                             details="Sender is not in EMAIL_REQUEST_SENDERS")
        return
    natural_request, candidates = parse_natural_request(text)
    if natural_request:
        if natural_request.get("needs_snapshot_id"):
            _send(
                sender, message.get("Subject", "OpsAgent clarification"),
                "Delete snapshot requires one exact snapshot ID. Example: Delete snapshot snap-0123456789abcdef0",
                message.get("Message-ID"),
            )
            email_metrics.record("acknowledged", message_id=message_id, sender=sender, subject=subject,
                                 details="Snapshot ID clarification sent")
        elif natural_request.get("needs_volume_id"):
            _send(
                sender, message.get("Subject", "OpsAgent clarification"),
                "Delete volume requires one exact volume ID. Example: Delete EBS volume vol-0123456789abcdef0",
                message.get("Message-ID"),
            )
            email_metrics.record("acknowledged", message_id=message_id, sender=sender, subject=subject,
                                 details="Volume ID clarification sent")
        elif natural_request.get("needs_target"):
            ops_log.write("gmail", "WARNING", "target_not_resolved",
                          f"Candidates={len(candidates)}; clarification will be sent", message_id)
            candidate_lines = "\n".join(
                f"- {row['server_name']} ({row['ip_address']}, {row['vm_type']})" for row in candidates
            ) or "- No matching enabled server was found."
            _send(
                sender, message.get("Subject", "OpsAgent clarification"),
                f"I understand that you want to {natural_request['action'].replace('_instance', '')}, "
                f"but I cannot identify one exact target.\n\nCandidates:\n{candidate_lines}\n\n"
                "Reply with a complete request such as: Start AWS-MS-OPSTESTVM",
                message.get("Message-ID"),
            )
            email_metrics.record("acknowledged", message_id=message_id, sender=sender, subject=subject,
                                 details="Target clarification sent")
        elif natural_request.get("unsupported_record"):
            row = natural_request["unsupported_record"]
            ops_log.write("gmail", "WARNING", "provider_not_supported",
                          f"Provider={row['vm_type']}; server={row['server_name']}", message_id)
            _send(sender, message.get("Subject", "OpsAgent clarification"),
                  f"I found {row['server_name']}, but native {row['vm_type']} power operations are not configured yet.",
                  message.get("Message-ID"))
            email_metrics.record("acknowledged", message_id=message_id, sender=sender, subject=subject,
                                 details="Unsupported-provider clarification sent")
        else:
            request_id = _new_request(sender, message, natural_request)
            ops_log.write("gmail", "INFO", "natural_request_acknowledged", request_id or "", message_id)
            email_metrics.record("acknowledged", message_id=message_id, sender=sender, subject=subject,
                                 request_id=request_id or "", details="Request acknowledgement sent")
        return
    _answer_read_only(sender, message, text)
    ops_log.write("gmail", "INFO", "read_only_response_sent", "Response workflow completed", message_id)
    email_metrics.record("acknowledged", message_id=message_id, sender=sender, subject=subject,
                         details="Read-only response sent")


def poll_once():
    ops_log.write("gmail", "INFO", "poll_started", f"Folder={config.IMAP_FOLDER}")
    with imaplib.IMAP4_SSL(config.IMAP_HOST, config.IMAP_PORT) as mailbox:
        mailbox.login(config.IMAP_USERNAME, config.IMAP_PASSWORD)
        ops_log.write("gmail", "INFO", "imap_login_succeeded", "Mailbox authentication succeeded")
        mailbox.select(config.IMAP_FOLDER)
        # Search recent mail regardless of Seen/Unread state. PostgreSQL
        # Message-ID deduplication guarantees at-most-once processing.
        since = (datetime.now(timezone.utc) - timedelta(minutes=config.INBOUND_EMAIL_LOOKBACK_MINUTES)).strftime("%d-%b-%Y")
        status, data = mailbox.search(None, "SINCE", since)
        if status != "OK":
            ops_log.write("gmail", "ERROR", "unread_search_failed", f"IMAP status={status}")
            return
        candidate_count = len(data[0].split())
        ops_log.write("gmail", "INFO", "recent_search_completed", f"Recent candidates={candidate_count}")
        processed_count = 0
        duplicate_count = 0
        expired_count = 0
        for message_number in data[0].split():
            status, payload = mailbox.fetch(message_number, "(RFC822)")
            if status == "OK" and payload and isinstance(payload[0], tuple):
                try:
                    parsed = email.message_from_bytes(payload[0][1])
                    message_id = parsed.get("Message-ID", "")
                    if email_metrics.was_received(message_id):
                        duplicate_count += 1
                        continue
                    try:
                        message_date = parsedate_to_datetime(parsed.get("Date", ""))
                        if message_date.tzinfo is None:
                            message_date = message_date.replace(tzinfo=timezone.utc)
                    except (TypeError, ValueError, OverflowError):
                        message_date = datetime.now(timezone.utc)
                    cutoff = datetime.now(timezone.utc) - timedelta(minutes=config.INBOUND_EMAIL_LOOKBACK_MINUTES)
                    if message_date.astimezone(timezone.utc) < cutoff:
                        expired_count += 1
                        continue
                    process_message(parsed)
                    processed_count += 1
                except Exception as exc:
                    ops_log.write("gmail", "ERROR", "message_processing_failed",
                                  f"{type(exc).__name__}: {exc}")
                    raise
            else:
                ops_log.write("gmail", "ERROR", "message_fetch_failed", f"IMAP status={status}")
        health_status.update("inbound_email", "healthy", f"Processed {processed_count} recent message(s)")
        ops_log.write("gmail", "INFO", "poll_completed",
                      f"Candidates={candidate_count}; processed={processed_count}; duplicates={duplicate_count}; outside lookback={expired_count}")


def start():
    if not config.INBOUND_EMAIL_ENABLED:
        ops_log.write("gmail", "WARNING", "listener_disabled", "INBOUND_EMAIL_ENABLED=false")
        return None
    missing = [name for name, value in {
        "IMAP_HOST": config.IMAP_HOST, "IMAP_USERNAME": config.IMAP_USERNAME,
        "IMAP_PASSWORD": config.IMAP_PASSWORD, "EMAIL_REQUEST_SENDERS": config.EMAIL_REQUEST_SENDERS,
        "EMAIL_APPROVERS": config.EMAIL_APPROVERS,
    }.items() if not value]
    if missing:
        ops_log.write("gmail", "ERROR", "listener_configuration_invalid", "Missing: " + ", ".join(missing))
        raise RuntimeError("Inbound email enabled but missing: " + ", ".join(missing))

    def worker():
        # One database-held lock prevents Streamlit and the Slack process from
        # polling the same mailbox and sending duplicate replies.
        with database.connect() as lease_connection:
            with lease_connection.cursor() as cursor:
                cursor.execute("SELECT pg_try_advisory_lock(824296731)")
                acquired = bool(cursor.fetchone()[0])
            if not acquired:
                ops_log.write("gmail", "WARNING", "listener_standby",
                              "Another OpsAgent process owns the Gmail listener lock")
                return
            ops_log.write("gmail", "INFO", "listener_lock_acquired",
                          "This process is the active Gmail consumer")
            while True:
                try:
                    poll_once()
                except Exception as exc:
                    email_metrics.record("failed", details=f"{type(exc).__name__}: {exc}")
                    ops_log.write("gmail", "ERROR", "poll_failed", f"{type(exc).__name__}: {exc}")
                    health_status.update("inbound_email", "error", exc)
                    print(f"[inbound_email] {type(exc).__name__}: {exc}")
                time.sleep(max(10, config.INBOUND_EMAIL_POLL_SECONDS))

    thread = threading.Thread(target=worker, name="inbound-email-listener", daemon=True)
    thread.start()
    ops_log.write("gmail", "INFO", "listener_started", f"Polling every {max(10, config.INBOUND_EMAIL_POLL_SECONDS)} seconds")
    return thread

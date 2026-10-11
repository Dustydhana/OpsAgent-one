"""Guarded Slack approval workflow for AWS EC2 power operations.

Slack messages can create approval requests, but this module never performs a
mutation until a configured approver sends the matching approval command.
Every workflow field is stored in relational PostgreSQL columns.
"""

import re
import secrets
import threading
from datetime import datetime, timedelta, timezone
from functools import lru_cache

import config
import database
import ops_log
import server_inventory
import slack_handler
from providers import aws


_ACTION_PATTERNS = (
    ("terminate_instance", r"(?:terminate|destroy|permanently\s+delete)\s+(?:an?\s+)?(?:ec2\s+)?(?:instance|server|vm)?\b"),
    ("delete_volume", r"(?:delete|remove)\s+(?:an?\s+)?(?:ebs\s+)?(?:volume|drive|disk)\b"),
    ("delete_snapshot", r"(?:delete|remove)\s+(?:an?\s+)?snapshot\b"),
    ("create_snapshot", r"(?:create|take)\s+(?:an?\s+)?snapshot\b"),
    ("reboot_instance", r"(?:reboot|restart)\b"),
    ("start_instance", r"(?:start|power\s+on|turn\s+on|boot\s+up)\b"),
    ("stop_instance", r"(?:stop|power\s+off|turn\s+off|shut\s*down)\b"),
)
_ACTION_LABELS = {
    "terminate_instance": "Permanently terminate EC2 instance",
    "start_instance": "Start",
    "stop_instance": "Stop",
    "reboot_instance": "Reboot",
    "create_snapshot": "Create EBS snapshot",
    "delete_snapshot": "Delete EBS snapshot",
    "delete_volume": "Delete EBS volume",
}
_SEEN_APPROVAL_MESSAGE_TS = set()
_SEEN_APPROVAL_LOCK = threading.Lock()


def _tenant_aws_credentials():
    import credential_store
    organization_id = str(config.DEFAULT_ORGANIZATION_ID or "").strip()
    if not organization_id:
        return None
    return credential_store.resolve_provider(organization_id, "aws")


def _tenant_allowed_actions():
    credentials = _tenant_aws_credentials() or {}
    stored = {value.strip() for value in credentials.get("allowed_actions", "").split(",") if value.strip()}
    return stored if credentials else set(config.AWS_ALLOWED_ACTIONS)


def parse_approval(text):
    """Return an approval ID only for an explicit APPROVE command."""
    clean = _without_slack_mention(text)
    match = re.search(r"(?im)^\s*APPROVE\s+(SLK-[0-9A-F]{8})\s*$", clean)
    return match.group(1).upper() if match else None


def _without_slack_mention(text):
    clean = re.sub(r"<@[A-Z0-9]+>", " ", text or "", flags=re.I)
    clean = re.sub(r"^\s*@?ops\s*agent\b\s*[:,;-]?", "", clean, flags=re.I)
    # Slack surrounds inline-code messages with backticks in event text.
    return clean.strip().strip("`").strip()


def parse_action_request(text):
    """Parse an explicitly phrased guarded AWS request and exact target."""
    clean = _without_slack_mention(text)
    action = None
    for name, pattern in _ACTION_PATTERNS:
        if re.match(rf"(?i)^\s*(?:please\s+|kindly\s+)?{pattern}", clean):
            action = name
            break
    if not action:
        return None

    if action == "delete_snapshot":
        snapshot_match = re.search(r"\bsnap-[0-9a-f]{8,17}\b", clean, re.I)
        if not snapshot_match:
            return {"action": action, "error": "snapshot_id_required"}
        region_match = re.search(r"\bregion=([a-z]{2}-[a-z]+-\d)\b", clean, re.I)
        snapshot_id = snapshot_match.group().lower()
        return {
            "action": action, "server_name": "EBS Snapshot",
            "provider": "aws", "resource_id": snapshot_id,
            "snapshot_id": snapshot_id,
            "region": region_match.group(1) if region_match else config.AWS_REGION,
        }

    if action == "delete_volume":
        volume_match = re.search(r"\bvol-[0-9a-f]{8,17}\b", clean, re.I)
        if not volume_match:
            return {"action": action, "error": "volume_id_required"}
        region_match = re.search(r"\bregion=([a-z]{2}-[a-z]+-\d)\b", clean, re.I)
        volume_id = volume_match.group().lower()
        return {
            "action": action, "server_name": "EBS Volume",
            "provider": "aws", "resource_id": volume_id,
            "volume_id": volume_id,
            "region": region_match.group(1) if region_match else config.AWS_REGION,
        }

    record = server_inventory.retrieve_for_alert(clean)
    if not record:
        return {"action": action, "error": "target_not_found"}
    if str(record.get("vm_type") or "").lower() != "aws" or not record.get("aws_instance_id"):
        return {
            "action": action,
            "error": "unsupported_target",
            "server_name": record.get("server_name") or "Unknown",
        }
    parsed = {
        "action": action,
        "server_name": record["server_name"],
        "provider": "aws",
        "resource_id": record["aws_instance_id"],
        "region": record.get("aws_region") or config.AWS_REGION,
    }
    if action == "create_snapshot":
        volume_match = re.search(r"\bvol-[0-9a-f]{8,17}\b", clean, re.I)
        parsed["volume_id"] = volume_match.group().lower() if volume_match else None
        parsed["description"] = f"OpsAgent Slack snapshot for {record['server_name']}"
    return parsed


@lru_cache(maxsize=100)
def _configured_approver_id(reference):
    try:
        return slack_handler.resolve_user_id(reference)
    except Exception:
        return None


def _is_authorized_approver(user_id):
    if not user_id:
        return False
    for reference in config.SLACK_APPROVERS:
        if user_id.casefold() == reference.casefold():
            return True
        resolved = _configured_approver_id(reference)
        if resolved and user_id.casefold() == resolved.casefold():
            return True
    return False


def _row_to_request(row):
    if not row:
        return None
    keys = (
        "request_id", "status", "requester", "requester_id", "approver",
        "approver_id", "action", "server_name", "provider", "resource_id",
        "volume_id", "snapshot_id", "description", "region", "channel_id", "thread_ts", "source_message_ts", "created_at",
        "expires_at", "approved_at", "executed_at", "before_state", "after_state",
        "success", "verified", "dry_run", "error_message",
    )
    return dict(zip(keys, row))


def _select_request(cursor, request_id, *, for_update=False):
    cursor.execute(f"""SELECT request_id,status,requester,requester_id,approver,
        approver_id,action,server_name,provider,resource_id,volume_id,snapshot_id,
        description,region,channel_id,
        thread_ts,source_message_ts,created_at,expires_at,approved_at,executed_at,
        before_state,after_state,success,verified,dry_run,error_message
        FROM ops_agent.slack_action_requests WHERE request_id=%s
        {'FOR UPDATE' if for_update else ''}""", (request_id,))
    return _row_to_request(cursor.fetchone())


def _create_request(parsed, channel, source_ts, thread_ts, requester_id):
    database.initialize()
    now = datetime.now(timezone.utc)
    request_id = f"SLK-{secrets.token_hex(4).upper()}"
    requester = slack_handler.requester_label(requester_id)
    expires_at = now + timedelta(minutes=config.SLACK_APPROVAL_EXPIRY_MINUTES)
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""INSERT INTO ops_agent.slack_action_requests
                (request_id,status,requester,requester_id,action,server_name,provider,
                 resource_id,volume_id,snapshot_id,description,region,channel_id,thread_ts,
                 source_message_ts,created_at,expires_at)
                VALUES (%s,'pending',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (channel_id,source_message_ts,action) DO NOTHING
                RETURNING request_id""", (
                request_id, requester, requester_id or "unknown", parsed["action"],
                parsed["server_name"], parsed["provider"], parsed["resource_id"],
                parsed.get("volume_id"), parsed.get("snapshot_id"), parsed.get("description"),
                parsed["region"], channel, thread_ts, source_ts, now, expires_at,
            ))
            inserted = cursor.fetchone()
            if not inserted:
                cursor.execute("""SELECT request_id FROM ops_agent.slack_action_requests
                    WHERE channel_id=%s AND source_message_ts=%s AND action=%s""",
                    (channel, source_ts, parsed["action"]))
                request_id = cursor.fetchone()[0]
        connection.commit()
    return request_id, requester, expires_at, bool(inserted)


def _state(identifier, region, client=None):
    description = aws.describe_instance(identifier, region, client)
    return str(description.get("state") or "unknown")


def _before_state(item, client=None):
    if item["action"] == "delete_volume":
        return str(aws.describe_volume(item["volume_id"], item["region"], client).get("state") or "unknown")
    if item["action"] == "delete_snapshot":
        return str(aws.describe_snapshot(item["snapshot_id"], item["region"], client).get("state") or "unknown")
    if item["action"] == "create_snapshot" and item.get("volume_id"):
        return str(aws.describe_volume(item["volume_id"], item["region"], client).get("state") or "unknown")
    return _state(item["resource_id"], item["region"], client)


def _update_execution(request_id, **values):
    allowed = {
        "status", "before_state", "after_state", "success", "verified",
        "dry_run", "error_message", "executed_at", "snapshot_id",
    }
    fields = [(key, value) for key, value in values.items() if key in allowed]
    if not fields:
        return
    assignments = ",".join(f"{key}=%s" for key, _value in fields)
    params = [value for _key, value in fields] + [request_id]
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"UPDATE ops_agent.slack_action_requests SET {assignments},updated_at=NOW() WHERE request_id=%s",
                params,
            )
        connection.commit()


def _execute(request_id):
    with database.connect() as connection:
        with connection.cursor() as cursor:
            item = _select_request(cursor, request_id)
    if not item or item["status"] != "executing":
        return

    before_state = None
    after_state = None
    verified = False
    error = None
    try:
        tenant_credentials = _tenant_aws_credentials()
        credentials = tenant_credentials or {}
        allowed_actions = (
            {value.strip() for value in credentials.get("allowed_actions", "").split(",") if value.strip()}
            if tenant_credentials else set(config.AWS_ALLOWED_ACTIONS)
        )
        execution_mode = credentials.get("execution_mode") or ("validation" if config.AWS_DRY_RUN else "live")
        client = aws.client_for_credentials(credentials, item["region"])
        before_state = _before_state(item, client)
        _update_execution(request_id, before_state=before_state)
        result = aws.execute(
            item["action"], item["resource_id"], approved=True,
            actor=f"slack:{item['approver_id']}", region=item["region"],
            request_id=request_id, source="slack", requester=item.get("requester"),
            approver=item.get("approver") or item.get("approver_id"),
            volume_id=item.get("volume_id"), snapshot_id=item.get("snapshot_id"),
            description=item.get("description"),
            client=client, organization_id=config.DEFAULT_ORGANIZATION_ID,
            dry_run=execution_mode != "live", allowed_actions=allowed_actions,
        )
        success = bool(result.get("success"))
        dry_run = bool(result.get("dry_run"))
        error = result.get("error")

        if success and dry_run:
            after_state = before_state
            verified = True
        elif success and item["action"] == "create_snapshot":
            created_snapshot = result.get("snapshot_id")
            if not created_snapshot:
                error = "AWS did not return a snapshot ID"
            else:
                snapshot = aws.describe_snapshot(created_snapshot, item["region"], client)
                after_state = str(snapshot.get("state") or "unknown")
                verified = after_state in {"pending", "completed"}
                _update_execution(request_id, snapshot_id=created_snapshot)
                item["snapshot_id"] = created_snapshot
        elif success and item["action"] == "delete_snapshot":
            verification = aws.wait_for_snapshot_deleted(
                item["snapshot_id"], region=item["region"],
                timeout=config.SLACK_AWS_VERIFY_SECONDS,
                client=client,
            )
            verified = bool(verification.get("verified"))
            after_state = verification.get("state") or "unknown"
            error = error or verification.get("error")
        elif success and item["action"] == "delete_volume":
            verification = aws.wait_for_volume_deleted(
                item["volume_id"], region=item["region"],
                timeout=config.SLACK_AWS_VERIFY_SECONDS,
                client=client,
            )
            verified = bool(verification.get("verified"))
            after_state = verification.get("state") or "unknown"
            error = error or verification.get("error")
        elif success and item["action"] in {"start_instance", "stop_instance"}:
            expected = "running" if item["action"] == "start_instance" else "stopped"
            verification = aws.wait_for_instance_state(
                item["resource_id"], expected, region=item["region"],
                timeout=config.SLACK_AWS_VERIFY_SECONDS,
                client=client,
            )
            verified = bool(verification.get("verified"))
            after_state = str((verification.get("instance") or {}).get("state") or "unknown")
            error = error or verification.get("error")
        elif success:
            after_state = _state(item["resource_id"], item["region"], client)
            verified = after_state == "running"

        status = "completed" if success and verified else "failed"
    except Exception as exc:
        success = False
        dry_run = bool(config.AWS_DRY_RUN)
        status = "failed"
        error = str(exc)

    executed_at = datetime.now(timezone.utc)
    _update_execution(
        request_id, status=status, before_state=before_state, after_state=after_state,
        success=success, verified=verified, dry_run=dry_run,
        error_message=error, executed_at=executed_at,
    )
    outcome = "COMPLETED" if status == "completed" else "FAILED"
    mode = "AWS dry-run validation; no state changed" if dry_run else "Live AWS operation"
    message = (
        f"{'✅' if status == 'completed' else '❌'} *{outcome}* — `{request_id}`\n"
        f"Action: *{_ACTION_LABELS[item['action']]}*\n"
        f"VM / Server: `{item['server_name']}`\n"
        f"Resource ID: `{item['resource_id']}`\n"
        f"{'Volume ID: `' + item['volume_id'] + '`' + chr(10) if item.get('volume_id') else ''}"
        f"{'Snapshot ID: `' + item['snapshot_id'] + '`' + chr(10) if item.get('snapshot_id') else ''}"
        f"State: `{before_state or 'unknown'}` → `{after_state or 'unknown'}`\n"
        f"Verification: `{'passed' if verified else 'failed'}`\nMode: {mode}"
    )
    if error:
        message += f"\nError: `{str(error)[:500]}`"
    slack_handler.post_message(item["channel_id"], message, thread_ts=item["thread_ts"])
    ops_log.write(
        "slack_actions", "INFO" if status == "completed" else "ERROR",
        "aws_action_completed" if status == "completed" else "aws_action_failed",
        f"{item['action']} {item['server_name']} {before_state}->{after_state}; {error or 'no error'}",
        request_id,
    )


def _slack_timestamp(value):
    try:
        return datetime.fromtimestamp(float(value), timezone.utc)
    except (TypeError, ValueError, OSError):
        return datetime.now(timezone.utc)


def _approve(request_id, channel, approver_id, *, approval_ts=None):
    database.initialize()
    if not _is_authorized_approver(approver_id):
        slack_handler.post_message(
            channel,
            f"⛔ Approval denied for `{request_id}`. Your Slack identity is not in `SLACK_APPROVERS`.",
        )
        ops_log.write("slack_actions", "WARNING", "approval_denied", f"user={approver_id}", request_id)
        return True

    now = datetime.now(timezone.utc)
    approval_time = _slack_timestamp(approval_ts) if approval_ts else now
    approver = slack_handler.requester_label(approver_id)
    with database.connect() as connection:
        with connection.cursor() as cursor:
            item = _select_request(cursor, request_id, for_update=True)
            if not item:
                outcome = "not_found"
            elif item["status"] not in {"pending", "expired"}:
                outcome = item["status"]
            elif approval_time > item["expires_at"]:
                cursor.execute("""UPDATE ops_agent.slack_action_requests
                    SET status='expired',updated_at=NOW() WHERE request_id=%s""", (request_id,))
                outcome = "expired"
            elif not config.SLACK_ALLOW_SELF_APPROVAL and approver_id == item["requester_id"]:
                outcome = "self_denied"
            else:
                cursor.execute("""UPDATE ops_agent.slack_action_requests SET
                    status='executing',approver=%s,approver_id=%s,approved_at=%s,updated_at=NOW()
                    WHERE request_id=%s""", (approver, approver_id, approval_time, request_id))
                outcome = "executing"
        connection.commit()

    if outcome == "not_found":
        slack_handler.post_message(channel, f"❌ Request `{request_id}` was not found.")
    elif outcome == "expired":
        slack_handler.post_message(channel, f"⌛ Request `{request_id}` expired and was not executed.")
    elif outcome == "self_denied":
        slack_handler.post_message(
            item["channel_id"],
            f"⛔ Self-approval is disabled for `{request_id}`. A different configured approver must approve it.",
            thread_ts=item["thread_ts"],
        )
    elif outcome != "executing":
        slack_handler.post_message(channel, f"ℹ️ Request `{request_id}` is already `{outcome}`.")
    else:
        slack_handler.post_message(
            item["channel_id"],
            f"✅ Approval accepted from {approver}. Executing `{request_id}` and verifying AWS state…",
            thread_ts=item["thread_ts"],
        )
        ops_log.write("slack_actions", "INFO", "approval_accepted", f"approver={approver}", request_id)
        threading.Thread(
            target=_execute, args=(request_id,), name=f"slack-action-{request_id}", daemon=True,
        ).start()
    return True


def handle_message(text, channel, ts, requester_id, *, thread_ts=None, mentioned=False):
    """Handle one human Slack message; return True when it is an action workflow message."""
    approval_id = parse_approval(text)
    if approval_id:
        return _approve(approval_id, channel, requester_id, approval_ts=ts)
    if not mentioned:
        return False

    parsed = parse_action_request(text)
    if not parsed:
        return False
    root_ts = thread_ts or ts
    if parsed.get("error") == "target_not_found":
        slack_handler.post_message(
            channel,
            "❌ I could not resolve one exact PostgreSQL inventory target. Use the exact VM/server name, IP, or AWS instance ID.",
            thread_ts=root_ts,
        )
        return True
    if parsed.get("error") == "unsupported_target":
        slack_handler.post_message(
            channel,
            f"❌ `{parsed['server_name']}` is not an AWS inventory record with an instance ID.",
            thread_ts=root_ts,
        )
        return True
    if parsed.get("error") == "snapshot_id_required":
        slack_handler.post_message(
            channel, "❌ Delete snapshot requires one exact ID such as `snap-0123456789abcdef0`.",
            thread_ts=root_ts,
        )
        return True
    if parsed.get("error") == "volume_id_required":
        slack_handler.post_message(
            channel, "❌ Delete volume requires one exact ID such as `vol-0123456789abcdef0`.",
            thread_ts=root_ts,
        )
        return True
    if parsed["action"] not in _tenant_allowed_actions():
        slack_handler.post_message(
            channel,
            f"⛔ `{parsed['action']}` is disabled in the AWS connection policy; no request was created. Enable it under Connections → AWS → Manage connection.",
            thread_ts=root_ts,
        )
        return True
    if not config.SLACK_APPROVERS:
        slack_handler.post_message(
            channel,
            "⛔ Slack cloud approvals are not configured. Set `SLACK_APPROVERS` first; no request was created.",
            thread_ts=root_ts,
        )
        return True

    request_id, requester, expires_at, inserted = _create_request(
        parsed, channel, ts, root_ts, requester_id,
    )
    if not inserted:
        return True
    destructive_warning = (
        "\n⚠️ Permanent deletion. The volume must be detached, available, explicitly tagged for deletion, "
        "and should have a recovery snapshot.\n"
        if parsed["action"] == "delete_volume" else ""
    )
    slack_handler.post_message(
        channel,
        f"📋 *REQUEST ACKNOWLEDGED — no AWS action has run*\n"
        f"Request ID: `{request_id}`\nRequester: {requester}\n"
        f"Action: *{_ACTION_LABELS[parsed['action']]}*\n"
        f"VM / Server: `{parsed['server_name']}`\n"
        f"Resource ID: `{parsed['resource_id']}`\nRegion: `{parsed['region']}`\n"
        f"{'Volume ID: `' + parsed['volume_id'] + '`' + chr(10) if parsed.get('volume_id') else ''}"
        f"{'Snapshot ID: `' + parsed['snapshot_id'] + '`' + chr(10) if parsed.get('snapshot_id') else ''}"
        f"{destructive_warning}"
        f"Expires: `{expires_at.astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')}`\n\n"
        f"A configured approver must reply with exactly: `APPROVE {request_id}`",
        thread_ts=root_ts,
    )
    ops_log.write(
        "slack_actions", "INFO", "request_created",
        f"requester={requester}; action={parsed['action']}; target={parsed['server_name']}", request_id,
    )
    return True


def history(limit=250):
    """Return newest Slack cloud requests for the operations dashboard."""
    database.initialize()
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""UPDATE ops_agent.slack_action_requests
                SET status='expired',updated_at=NOW()
                WHERE status='pending' AND expires_at < NOW()""")
            cursor.execute("""SELECT request_id,status,requester,requester_id,approver,
                approver_id,action,server_name,provider,resource_id,volume_id,snapshot_id,
                description,region,channel_id,
                thread_ts,source_message_ts,created_at,expires_at,approved_at,executed_at,
                before_state,after_state,success,verified,dry_run,error_message
                FROM ops_agent.slack_action_requests ORDER BY created_at DESC LIMIT %s""",
                (max(1, min(int(limit), 1000)),))
            rows = [_row_to_request(row) for row in cursor.fetchall()]
        connection.commit()
    return rows


def _pending_requests():
    database.initialize()
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""UPDATE ops_agent.slack_action_requests
                SET status='expired',updated_at=NOW()
                WHERE status='pending' AND expires_at < NOW()""")
            cursor.execute("""SELECT request_id,status,requester,requester_id,approver,
                approver_id,action,server_name,provider,resource_id,volume_id,snapshot_id,
                description,region,channel_id,
                thread_ts,source_message_ts,created_at,expires_at,approved_at,executed_at,
                before_state,after_state,success,verified,dry_run,error_message
                FROM ops_agent.slack_action_requests
                WHERE status IN ('pending','expired')
                  AND approved_at IS NULL AND created_at > NOW() - INTERVAL '1 hour'
                ORDER BY created_at""")
            rows = [_row_to_request(row) for row in cursor.fetchall()]
        connection.commit()
    return rows


def recover_pending_thread_approvals():
    """Recover approvals from thread history when Slack misses a message event."""
    recovered = 0
    for item in _pending_requests():
        response = slack_handler.app.client.conversations_replies(
            channel=item["channel_id"], ts=item["thread_ts"], limit=100,
        )
        for message in response.get("messages", [])[1:]:
            message_ts = message.get("ts")
            if not message_ts or message.get("bot_id") or message.get("subtype"):
                continue
            with _SEEN_APPROVAL_LOCK:
                if message_ts in _SEEN_APPROVAL_MESSAGE_TS:
                    continue
            if parse_approval(message.get("text") or "") != item["request_id"]:
                continue
            with _SEEN_APPROVAL_LOCK:
                _SEEN_APPROVAL_MESSAGE_TS.add(message_ts)
            _approve(
                item["request_id"], item["channel_id"], message.get("user"),
                approval_ts=message_ts,
            )
            recovered += 1
            break
    if recovered:
        ops_log.write(
            "slack_actions", "INFO", "thread_approvals_recovered",
            f"Recovered {recovered} approval message(s) from Slack thread history",
        )
    return recovered

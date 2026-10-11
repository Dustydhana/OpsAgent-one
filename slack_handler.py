"""
slack_handler.py
------------------
All Slack I/O: listening for alert messages (via Socket Mode, so no public
HTTPS endpoint is needed) and posting messages/incident reports back.
"""

import os
import re
import time
import threading
from functools import lru_cache

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

import config
import health_status
import retry_policy

# Single shared Bolt app instance for the whole process. Avoid Slack's eager
# auth.test during import so the standalone Streamlit dashboard can start when
# Slack is temporarily unreachable. start() performs an explicit auth_test.
app = App(token=config.SLACK_BOT_TOKEN, token_verification_enabled=False)

# Resolved lazily in start() once the bot is authenticated.
_target_channel_id = None
_channel_id_cache = {}
_bot_user_id = None
_registered_on_alert = None
_registered_on_mention = None
_registered_on_action = None
_registered_action_recovery = None
_last_processed_alert_ts = {}
_seen_human_mention_ts = set()


def resolve_channel_id(channel_name):
    """
    Slack events report channel IDs, but humans configure a channel name
    (e.g. '#ops-alerts'). Look up the ID once and cache it.
    """
    name = channel_name.lstrip("#")
    if name in _channel_id_cache:
        return _channel_id_cache[name]

    cursor = None
    while True:
        resp = app.client.conversations_list(
            types="public_channel", cursor=cursor, limit=200
        )
        for channel in resp["channels"]:
            if channel["name"] == name:
                _channel_id_cache[name] = channel["id"]
                return channel["id"]
        cursor = resp.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break

    raise ValueError(
        f"Could not find a Slack channel named '{channel_name}'. "
        "Make sure the bot has been invited to it."
    )


def post_message(channel, text, blocks=None, thread_ts=None):
    """Post a message to Slack. Logs to stdout on failure instead of raising,
    so a Slack hiccup never crashes the agent mid-incident."""
    try:
        payload = {"channel": channel, "text": text}
        if blocks is not None:
            payload["blocks"] = blocks
        if thread_ts is not None:
            payload["thread_ts"] = thread_ts
        retry_policy.run(lambda: app.client.chat_postMessage(**payload), attempts=config.RETRY_ATTEMPTS, delay=config.RETRY_DELAY_SECONDS)
        return True
    except Exception as e:
        print(f"[slack_handler] Failed to post message to {channel}: {e}")
        return False


@lru_cache(maxsize=500)
def requester_label(user_id):
    """Return a stable human-readable Slack audit identity."""
    if not user_id or user_id == "Grafana Alerts":
        return user_id or "Unknown"
    try:
        member = app.client.users_info(user=user_id).get("user", {})
        profile = member.get("profile", {})
        name = profile.get("real_name") or profile.get("display_name") or member.get("name")
        return f"{name} ({user_id})" if name else user_id
    except Exception:
        return user_id


def _split_markdown_row(line):
    """Split a pipe table row while preserving escaped pipes inside cells."""
    content = line.strip().strip("|")
    cells = re.split(r"(?<!\\)\|", content)
    return [cell.strip().replace("\\|", "|").replace("`", "") for cell in cells]


def structured_report_parts(markdown_text):
    """Convert report Markdown into narrative chunks and Slack table blocks."""
    lines = (markdown_text or "").splitlines()
    parts, narrative, index = [], [], 0

    def flush_narrative():
        text = "\n".join(narrative).strip()
        if text:
            # Slack mrkdwn uses bold rather than Markdown heading markers.
            text = re.sub(r"(?m)^###\s+(.+)$", r"*\1*", text)
            parts.append(("text", text))
        narrative.clear()

    while index < len(lines):
        if lines[index].lstrip().startswith("|"):
            table_lines = []
            while index < len(lines) and lines[index].lstrip().startswith("|"):
                table_lines.append(lines[index]); index += 1
            if len(table_lines) >= 2:
                flush_narrative()
                rows = [_split_markdown_row(line) for line in table_lines]
                rows = [row for row in rows if not all(re.fullmatch(r":?-+:?", cell) for cell in row)]
                if rows:
                    width = min(len(rows[0]), 20)
                    rows = [row[:width] + [""] * max(width - len(row), 0) for row in rows[:100]]
                    parts.append(("table", rows))
            continue
        narrative.append(lines[index]); index += 1
    flush_narrative()
    return parts


def post_structured_report(channel, markdown_text, thread_ts=None):
    """Post Streamlit-equivalent report sections with native Slack tables."""
    for kind, payload in structured_report_parts(markdown_text):
        if kind == "text":
            post_message(channel, payload, thread_ts=thread_ts)
            continue
        rows = [[{"type": "raw_text", "text": str(cell)[:1000]} for cell in row] for row in payload]
        block = {
            "type": "table", "rows": rows,
            "column_settings": [{"align": "left", "is_wrapped": True} for _ in rows[0]],
        }
        try:
            retry_policy.run(
                lambda: app.client.chat_postMessage(channel=channel, text="Structured investigation table",
                                                    blocks=[block], thread_ts=thread_ts),
                attempts=config.RETRY_ATTEMPTS, delay=config.RETRY_DELAY_SECONDS,
            )
        except Exception as exc:
            print(f"[slack_handler] Native table failed, using text fallback: {exc}")
            widths = [max(len(row[col]) for row in payload) for col in range(len(payload[0]))]
            fallback = "\n".join(" | ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)) for row in payload)
            post_message(channel, f"```{fallback[:2800]}```", thread_ts=thread_ts)


def upload_image_to_slack(channel, image_path, title, initial_comment=None, thread_ts=None):
    """Upload an image to Slack and remove the temporary file afterward."""
    try:
        payload = {"channel": channel, "file": image_path, "title": title}
        if initial_comment:
            payload["initial_comment"] = initial_comment
        if thread_ts:
            payload["thread_ts"] = thread_ts
        response = retry_policy.run(lambda: app.client.files_upload_v2(**payload), attempts=config.RETRY_ATTEMPTS, delay=config.RETRY_DELAY_SECONDS)
        return {"ok": True, "response": response, "error": None}
    except Exception as e:
        print(f"[slack_handler] Failed to upload image '{image_path}' to {channel}: {e}")
        return {"ok": False, "response": None, "error": str(e)}
    finally:
        try:
            if image_path and os.path.exists(image_path):
                os.remove(image_path)
        except OSError as exc:
            print(f"[slack_handler] Failed to remove temp image '{image_path}': {exc}")


def _is_bot_mention(text):
    content = (text or "").lower()
    if _bot_user_id and f"<@{_bot_user_id.lower()}>" in content:
        return True
    return "ops agent" in content


def _slack_event_text(event):
    """Flatten normal Slack text and webhook attachment content."""
    parts = []
    if event.get("text"):
        parts.append(str(event["text"]))
    for attachment in event.get("attachments") or []:
        for key in ("title", "fallback", "text"):
            value = attachment.get(key)
            if value:
                parts.append(str(value))
        for field in attachment.get("fields") or []:
            if field.get("title"):
                parts.append(str(field["title"]))
            if field.get("value"):
                parts.append(str(field["value"]))
    return "\n".join(dict.fromkeys(parts)).strip()


def _is_grafana_firing_event(event):
    """Accept only firing alerts from the dedicated Grafana Slack app."""
    text = _slack_event_text(event)
    bot_profile = event.get("bot_profile") or {}
    bot_name = (bot_profile.get("name") or event.get("username") or "").strip()
    is_grafana_source = (
        bot_name.casefold() == config.GRAFANA_SLACK_BOT_NAME.casefold()
        or "grafana_folder" in text.casefold()
    )
    return (
        bool(event.get("bot_id"))
        and is_grafana_source
        and bool(re.search(r"(?mi)^\[FIRING(?:[:\]])", text))
    )


def _grafana_alert_key(text):
    """Return a stable key shared by FIRING and RESOLVED messages."""
    match = re.search(r"(?mi)^\[(?:FIRING|RESOLVED)(?::\d+)?\]\s*([^\r\n]+)", text or "")
    if match:
        return match.group(1).strip().casefold()
    match = re.search(r"(?mi)^\s*-\s*alertname\s*=\s*([^\r\n]+)", text or "")
    return match.group(1).strip().casefold() if match else None


def recover_active_alerts(on_alert):
    """Replay recent Grafana alerts still firing when the listener starts."""
    if not _target_channel_id or config.STARTUP_ALERT_LOOKBACK_MINUTES <= 0:
        return 0
    oldest = time.time() - (config.STARTUP_ALERT_LOOKBACK_MINUTES * 60)
    response = app.client.conversations_history(
        channel=_target_channel_id, oldest=str(oldest), limit=200, inclusive=True
    )
    active = {}
    # Slack returns newest first; apply state transitions chronologically.
    for event in reversed(response.get("messages", [])):
        text = _slack_event_text(event)
        key = _grafana_alert_key(text)
        if not key:
            continue
        if re.search(r"(?mi)^\[RESOLVED(?:[:\]])", text):
            active.pop(key, None)
        elif _is_grafana_firing_event(event):
            active[key] = event
    active_keys = set(active)
    for stale_key in set(_last_processed_alert_ts) - active_keys:
        _last_processed_alert_ts.pop(stale_key, None)
    new_keys = [
        key for key, event in active.items()
        if _last_processed_alert_ts.get(key) != event.get("ts")
    ]
    for key in new_keys:
        event = active[key]
        _last_processed_alert_ts[key] = event.get("ts")
        on_alert(_slack_event_text(event), _target_channel_id, event.get("ts"), requester="Grafana Alerts")
    if new_keys:
        print(f"[slack_handler] Recovered {len(new_keys)} new active Grafana alert(s) from channel history")
    return len(new_keys)


def recover_human_mentions(on_alert, on_mention=None, on_action=None):
    """Recover tagged human requests when Socket Mode message delivery is missed."""
    if not _target_channel_id:
        return 0
    oldest = time.time() - (max(config.HUMAN_MENTION_LOOKBACK_MINUTES, 1) * 60)
    response = app.client.conversations_history(
        channel=_target_channel_id, oldest=str(oldest), limit=100, inclusive=True
    )
    recovered = 0
    for event in reversed(response.get("messages", [])):
        if event.get("bot_id") or event.get("subtype"):
            continue
        text, ts = event.get("text") or "", event.get("ts")
        if not ts or ts in _seen_human_mention_ts or not _is_bot_mention(text):
            continue
        _seen_human_mention_ts.add(ts)
        if on_action and on_action(
            text, _target_channel_id, ts, event.get("user"),
            thread_ts=event.get("thread_ts"), mentioned=True,
        ):
            recovered += 1
            continue
        lowered = text.lower()
        if _is_investigation_request(text) or any(keyword in lowered for keyword in config.ALERT_KEYWORDS):
            on_alert(text, _target_channel_id, ts, requester=event.get("user"))
        elif on_mention:
            on_mention(text, _target_channel_id, ts)
        recovered += 1
    if recovered:
        print(f"[slack_handler] Recovered {recovered} tagged human request(s) from channel history")
    return recovered


def _history_poll_worker(on_alert, on_mention=None, on_action=None, action_recovery=None):
    """Fallback for workspaces where message event delivery is unavailable."""
    while True:
        time.sleep(max(config.SLACK_ALERT_POLL_SECONDS, 10))
        try:
            recover_active_alerts(on_alert)
            recover_human_mentions(on_alert, on_mention, on_action)
            if action_recovery:
                action_recovery()
            health_status.update("grafana_polling", "healthy", f"Polling every {max(config.SLACK_ALERT_POLL_SECONDS, 10)} seconds")
        except Exception as exc:
            health_status.update("grafana_polling", "error", exc)
            print(f"[slack_handler] Alert history poll failed: {exc}")


def _is_investigation_request(text):
    lowered = (text or "").lower()
    return any(term in lowered for term in (
        "cpu", "memory", "ram", "disk", "storage", "patch", "update",
        "service", "logs", "health", "up or down", "server down", "server is down",
    ))


def _handle_incoming_text(raw_text, channel, ts, logger, on_alert, on_mention=None,
                          on_action=None, force_mention=False, requester=None,
                          thread_ts=None):
    text = (raw_text or "").lower()
    # Receiving an authenticated Socket Mode event is definitive proof that
    # the Slack connector is working. Clear any stale startup/channel lookup
    # error that may still be stored in component health.
    try:
        health_status.update("slack", "healthy", f"Live Socket Mode event received from channel {channel}")
    except Exception:
        logger.exception("Could not refresh Slack connector health")
    # Slack has already authenticated and classified app_mention events. Trust
    # that event type even if auth_test did not populate _bot_user_id yet.
    mention = force_mention or _is_bot_mention(raw_text)
    in_alert_channel = not _target_channel_id or channel == _target_channel_id

    # Cloud mutations get first refusal so "start server" cannot accidentally
    # enter the alert-investigation path. The callback only creates a pending
    # approval request; it never performs a direct mutation.
    if on_action and in_alert_channel:
        try:
            if on_action(
                raw_text, channel, ts, requester,
                thread_ts=thread_ts, mentioned=mention,
            ):
                return
        except Exception:
            logger.exception("Error while handling guarded Slack cloud action")
            return

    if any(keyword in text for keyword in config.ALERT_KEYWORDS) and in_alert_channel:
        try:
            on_alert(raw_text, channel, ts, requester=requester)
        except Exception:
            logger.exception("Error while handling alert from Slack message")
        return

    if mention and _is_investigation_request(raw_text) and in_alert_channel:
        try:
            on_alert(raw_text, channel, ts, requester=requester)
        except Exception:
            logger.exception("Error while handling requested investigation")
        return

    if mention and on_mention:
        try:
            on_mention(raw_text, channel, ts)
        except Exception:
            logger.exception("Error while handling bot mention from Slack message")


def resolve_user_id(user_reference):
    """Resolve a Slack ID, username, display name, or email-like reference."""
    reference = (user_reference or "").strip().lstrip("@").strip("<>")
    if reference.startswith(("U", "W")) and reference.isalnum():
        return reference
    cursor = None
    while True:
        response = app.client.users_list(cursor=cursor, limit=200)
        for member in response.get("members", []):
            profile = member.get("profile", {})
            candidates = {member.get("name"), profile.get("display_name"), profile.get("real_name"), profile.get("email")}
            if reference.lower() in {str(value).lower() for value in candidates if value}:
                return member["id"]
        cursor = response.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            return None


def notify_oncall(channel, host, issues, agent_result):
    """Post a high-priority channel alert and send the on-call engineer a DM."""
    user_id = None
    try:
        user_id = resolve_user_id(config.ONCALL_SLACK_USER)
    except Exception as exc:
        print(f"[slack_handler] Could not resolve on-call user: {exc}")
    mention = f"<@{user_id or config.ONCALL_SLACK_USER}>"
    issue_text = "\n".join(f"• {issue}" for issue in (issues or ["Server is unreachable or unhealthy"]))
    actions = agent_result.get("actions_taken", [])
    attempted = ", ".join(action.get("tool", "unknown") for action in actions) or "None"
    text = (
        f"🚨 HIGH PRIORITY — Server {host} is DOWN\n\nIssue detected:\n{issue_text}\n\n"
        f"{mention} — You are on-call. Please check this server immediately!\n\n"
        f"Attempted auto-remediation: {attempted}\nStatus: Manual intervention required."
    )
    post_message(channel, text)
    if user_id:
        post_message(user_id, text)


def register_alert_listener(on_alert, on_mention=None, on_action=None, action_recovery=None):
    """
    Register the handler that watches every message event in the workspace
    and triggers on_alert(text, channel, ts, requester=...) when an alert appears
    in the configured channel.
    """

    global _registered_on_alert, _registered_on_mention, _registered_on_action
    global _registered_action_recovery
    _registered_on_alert = on_alert
    _registered_on_mention = on_mention
    _registered_on_action = on_action
    _registered_action_recovery = action_recovery

    @app.event("message")
    def handle_message_events(event, logger):
        # The dedicated Grafana app is the sole bot allowed to trigger an
        # investigation. Resolved alerts and OpsAgent's own replies are ignored.
        if event.get("bot_id"):
            if _is_grafana_firing_event(event):
                channel = event.get("channel")
                in_alert_channel = not _target_channel_id or channel == _target_channel_id
                if in_alert_channel:
                    try:
                        key = _grafana_alert_key(_slack_event_text(event))
                        if key:
                            _last_processed_alert_ts[key] = event.get("ts")
                        on_alert(_slack_event_text(event), channel, event.get("ts"), requester="Grafana Alerts")
                    except Exception:
                        logger.exception("Error while handling Grafana alert")
            return

        # Ignore edits, deletes, and other non-human message subtypes.
        if event.get("subtype"):
            return

        if event.get("ts") and _is_bot_mention(event.get("text") or ""):
            _seen_human_mention_ts.add(event["ts"])

        _handle_incoming_text(
            event.get("text") or "",
            event.get("channel"),
            event.get("ts"),
            logger,
            on_alert,
            on_mention=on_mention,
            on_action=on_action,
            requester=event.get("user"),
            thread_ts=event.get("thread_ts"),
        )

    @app.event("app_mention")
    def handle_app_mentions(event, logger):
        if event.get("ts"):
            _seen_human_mention_ts.add(event["ts"])
        _handle_incoming_text(
            event.get("text") or "",
            event.get("channel"),
            event.get("ts"),
            logger,
            on_alert,
            on_mention=on_mention,
            on_action=on_action,
            force_mention=True,
            requester=event.get("user"),
            thread_ts=event.get("thread_ts"),
        )


def start():
    """Resolve the target channel and start the Socket Mode connection (blocking)."""
    global _target_channel_id, _bot_user_id
    try:
        auth = app.client.auth_test()
        _bot_user_id = auth.get("user_id")
        _target_channel_id = resolve_channel_id(config.SLACK_CHANNEL)
        print(
            f"[slack_handler] Watching channel '{config.SLACK_CHANNEL}' "
            f"(id={_target_channel_id}) as bot user {_bot_user_id}"
        )
        health_status.update("slack", "healthy", f"Authenticated as {_bot_user_id}; channel {_target_channel_id}")
    except Exception as e:
        print(
            f"[slack_handler] Warning: could not resolve channel '{config.SLACK_CHANNEL}' ({e}). "
            "Falling back to listening on every channel this bot is a member of."
        )
        _target_channel_id = None
        health_status.update("slack", "error", e)

    if _target_channel_id and _registered_on_alert:
        try:
            recover_active_alerts(_registered_on_alert)
            recover_human_mentions(
                _registered_on_alert, _registered_on_mention, _registered_on_action
            )
            if _registered_action_recovery:
                _registered_action_recovery()
        except Exception as e:
            print(f"[slack_handler] Warning: could not recover existing alerts ({e}). Live listening will continue.")
        threading.Thread(
            target=_history_poll_worker,
            args=(
                _registered_on_alert, _registered_on_mention,
                _registered_on_action, _registered_action_recovery,
            ),
            name="slack-alert-history-poller",
            daemon=True,
        ).start()
        print(f"[slack_handler] History fallback polling every {max(config.SLACK_ALERT_POLL_SECONDS, 10)} seconds")

    handler = SocketModeHandler(app, config.SLACK_APP_TOKEN)
    handler.start()

"""Slack entry point and reusable OpsAgent investigation pipeline."""

import threading
import traceback
import re
import queue
import time
import json
from datetime import datetime, timezone

import agent
import alert_metrics
import health_status
import chart_generator
import config
import diagnostics
import decommission_inventory
import email_handler
import inbound_email
import metrics_history
import os_detector
import remediation
import report
import network_diagnostics
import server_inventory
import slack_handler
import slack_actions
import ssh_handler

_incident_lock = threading.Lock()
_alert_queue = queue.Queue()
_alert_worker_started = False
_alert_worker_lock = threading.Lock()
_active_alert_keys = set()
_completed_alert_times = {}
_alert_state_lock = threading.Lock()
_pending_rechecks = set()
_pending_rechecks_lock = threading.Lock()


def _pct(value):
    return "N/A" if value is None else f"{value:.0f}%"


def _utilization_trend(host, request_mode):
    metric = {
        "cpu_query": ("CPU", "cpu_percent"),
        "memory_query": ("Memory", "memory_percent"),
        "disk_query": ("Disk", "disk_percent"),
    }.get(request_mode)
    if not metric:
        return ""
    label, key = metric

    def average(hours):
        values = [item.get(key) for item in metrics_history.load_recent(host, hours=hours)]
        values = [float(value) for value in values if value is not None]
        return (sum(values) / len(values), len(values)) if values else (None, 0)

    one_hour, one_count = average(1)
    day, day_count = average(24)
    one_text = "N/A" if one_hour is None else f"{one_hour:.1f}% ({one_count} sample(s))"
    day_text = "N/A" if day is None else f"{day:.1f}% ({day_count} sample(s))"
    return f"📈 Observed {label} trend — last 1 hour: {one_text} | last 24 hours: {day_text}"


def schedule_utilization_recheck(result, alert_text, request_mode, channel=None, thread_ts=None,
                                 breached_resources=None, delay_seconds=None, schedule_label=None):
    """Schedule one delayed utilization verification and email only if still high."""
    delay_seconds = config.UTILIZATION_RECHECK_SECONDS if delay_seconds is None else max(1, int(delay_seconds))
    schedule_label = schedule_label or "5-minute recheck"
    original = set(breached_resources or ())
    if not original:
        original = {label for label, _value in email_handler.utilization_breaches(result)}
    if not original:
        return False
    key = (result["host"], request_mode)
    with _pending_rechecks_lock:
        if key in _pending_rechecks:
            return False
        _pending_rechecks.add(key)

    def recheck():
        try:
            followup = investigate(
                alert_text,
                host=result["host"],
                os_preference=result["os_type"],
                request_mode=request_mode,
            )
            followup_metrics = followup["diagnostics_after"].get("metrics", {})
            metrics_history.record_sample(followup["host"], followup["os_type"], followup_metrics)
            persistent = [item for item in email_handler.utilization_breaches(followup) if item[0] in original]
            if persistent:
                values = ", ".join(f"{label} {value:.1f}%" for label, value in persistent)
                email_status = email_handler.send_utilization_alert_email(
                    followup, f"Persistent at scheduled recheck ({schedule_label}): {alert_text}"
                )
                message = f"🚨 Utilization remains high at the scheduled recheck: {values}."
                if email_status.get("sent"):
                    message += f" Email sent to `{email_status['recipient']}`."
                else:
                    message += f" Email not sent: {email_status.get('reason') or email_status.get('error', 'unknown error')}."
                if channel:
                    slack_handler.post_message(channel, message, thread_ts=thread_ts)
                else:
                    print(f"[utilization_recheck] {message}")
            else:
                message = "✅ Utilization is below 75% at the scheduled recheck. No escalation email was sent."
                if channel:
                    slack_handler.post_message(channel, message, thread_ts=thread_ts)
                else:
                    print(f"[utilization_recheck] {message}")
        except Exception as exc:
            message = f"⚠️ Scheduled utilization recheck failed: {exc}"
            if channel:
                slack_handler.post_message(channel, message, thread_ts=thread_ts)
            else:
                print(f"[utilization_recheck] {message}")
        finally:
            with _pending_rechecks_lock:
                _pending_rechecks.discard(key)

    timer = threading.Timer(delay_seconds, recheck)
    timer.daemon = True
    timer.start()
    return True


def _missing_target_message():
    return (
        "I can help investigate a specific server alert. Please send the server IP/hostname "
        "or paste the alert message that includes the target.\n\n"
        "Example: `@Ops agent check server 44.200.233.80`"
    )


def _is_disk_question(text):
    lowered = (text or "").lower()
    if "[firing" in lowered and re.search(r"alertname\s*=.*disk|opsagent[-_].*disk", lowered):
        return True
    disk_terms = ("disk", "storage", "space")
    query_terms = ("can you", "could you", "what", "which", "show", "tell me", "check", "?")
    detail_terms = ("consum", "usage", "utilization", "largest", "top", "folder", "file")
    return (
        any(term in lowered for term in disk_terms)
        and any(term in lowered for term in query_terms)
        and any(term in lowered for term in detail_terms)
    )


def _is_patch_question(text):
    lowered = (text or "").lower()
    return any(term in lowered for term in ("patch", "patches", "update", "updates", "hotfix"))


def _is_logs_question(text):
    lowered = (text or "").lower()
    return any(term in lowered for term in ("log", "logs", "error", "errors", "recent errors"))


def _is_services_question(text):
    lowered = (text or "").lower()
    return any(term in lowered for term in ("service", "services", "failed service", "important service"))


def _is_monitoring_question(text):
    lowered = (text or "").lower()
    return any(term in lowered for term in (
        "monitoring", "telemetry", config.MONITORING_SERVICE_NAME.lower(),
        "datasourcenodata", "datasource no data", "no metrics", "metrics missing",
        "not receiving metrics", "exporter down", "exporter not reporting",
    ))


def _is_summary_question(text):
    lowered = (text or "").lower()
    return any(term in lowered for term in (
        "summarize", "summary", "simple words", "what is happening",
        "full server overview", "server overview a-z", "server overview a to z",
    ))


def _is_full_overview_question(text):
    lowered = (text or "").lower()
    return any(term in lowered for term in (
        "full server overview", "server overview a-z", "server overview a to z",
    )) or bool(re.search(
        r"\bfull\s+server\b.{0,100}\boverview\b|\boverview\s+(?:a-z|a\s+to\s+z)\b",
        lowered,
    ))


def _is_reboot_question(text):
    lowered = (text or "").lower()
    return any(term in lowered for term in (
        "nodehasrebooted", "has rebooted", "server reboot", "server restart",
        "reboot detected", "reboot investigation",
    ))


def _is_cpu_question(text):
    return any(term in (text or "").lower() for term in ("cpu", "processor", "processing utilization"))


def _is_memory_question(text):
    return any(term in (text or "").lower() for term in ("memory", "ram"))


def _is_health_question(text):
    lowered = (text or "").lower()
    return any(term in lowered for term in (
        "server is down", "server down", "windowsserverdown", "server unreachable",
        "up or down", "health check", "server health", "server down investigation",
    ))


def _detect_request_mode(text):
    if _is_reboot_question(text):
        return "reboot_query"
    # The explicit dashboard A-Z option contains words such as patches/logs,
    # so recognize it before focused checks. Do not use Grafana's generic
    # `summary = ...` annotation for this decision.
    if _is_full_overview_question(text):
        return "summary_query"
    if _is_disk_question(text):
        return "disk_query"
    if _is_patch_question(text):
        return "patch_query"
    if _is_cpu_question(text):
        return "cpu_query"
    if _is_memory_question(text):
        return "memory_query"
    if _is_health_question(text):
        return "health_query"
    if _is_logs_question(text):
        return "logs_query"
    if _is_services_question(text):
        return "services_query"
    if _is_monitoring_question(text):
        return "monitoring_query"
    if _is_summary_question(text) and "grafana_folder" not in (text or "").lower():
        return "summary_query"
    return "incident"


def _format_disk_scan_lines(disk_scan, limit=5):
    lines = []
    for index, item in enumerate(disk_scan[:limit], start=1):
        lines.append(f"{index}. `{item.get('folder', 'unknown')}` — {float(item.get('size_gb', 0) or 0):.2f} GB")
    return "\n".join(lines) if lines else "No folder-level disk scan data was available."


def _format_service_lines(failed_output, limit=5):
    lines = [line.strip() for line in (failed_output or "").splitlines() if line.strip()]
    lines = [line for line in lines if not set(line) <= {"-", " "} and line.lower().replace(" ", "") not in {"namestatus", "unitloadactivesubdescription"}]
    if not lines or any("0 loaded units listed" in line for line in lines):
        return "No failed services were detected."
    rows = []
    for line in lines[:limit]:
        parts = line.rsplit(None, 1)
        name, status = (parts[0], parts[1]) if len(parts) == 2 else (line, "Unknown")
        rows.append(f"| `{_table_cell(name)}` | {_table_cell(status)} |")
    return "| Service | Status |\n|---|---|\n" + "\n".join(rows)


def _table_cell(value, limit=500):
    text = " ".join(str(value or "N/A").split()).replace("|", "\\|")
    return text[:limit] + ("..." if len(text) > limit else "")


def _format_log_lines(log_output, limit=5):
    raw = (log_output or "").strip()
    if not raw:
        return "No recent log entries were returned."
    # PowerShell Format-List output: group fields into events instead of
    # numbering timestamp/source/message as unrelated lines.
    events = []
    try:
        payload = json.loads(raw)
        if isinstance(payload, dict):
            payload = [payload]
        if isinstance(payload, list):
            events = [{str(key).lower(): value for key, value in item.items()} for item in payload if isinstance(item, dict)]
    except json.JSONDecodeError:
        pass
    current = {}
    last_field = None
    for raw_line in ([] if events else raw.splitlines()):
        line = raw_line.strip()
        match = re.match(r"^(TimeGenerated|TimeCreated|Source|ProviderName|EventID|Id|LevelDisplayName|Message)\s*:\s*(.*)$", line, re.I)
        if match:
            field, value = match.group(1).lower(), match.group(2).strip()
            if field in {"timegenerated", "timecreated"} and current:
                events.append(current)
                current = {}
            current[field] = value
            last_field = field
        elif line and last_field:
            current[last_field] = f"{current.get(last_field, '')} {line}".strip()
    if current:
        events.append(current)
    if not events:
        lines = [line.strip() for line in raw.splitlines() if line.strip()]
        rows = "\n".join(f"| {index} | {_table_cell(line)} |" for index, line in enumerate(lines[:limit], 1))
        return "| Entry | Message |\n|---:|---|\n" + rows
    formatted = []
    for event in events[:limit]:
        timestamp = event.get("timegenerated") or event.get("timecreated") or "Unknown time"
        source = event.get("source") or event.get("providername") or "Unknown source"
        event_id = event.get("eventid") or event.get("id")
        level = event.get("leveldisplayname") or event.get("level") or "N/A"
        message = event.get("message") or "No message returned."
        formatted.append(
            f"| {_table_cell(timestamp, 80)} | {_table_cell(event_id or 'N/A', 30)} | {_table_cell(level, 40)} | "
            f"{_table_cell(source, 100)} | {_table_cell(message)} |"
        )
    return "| Time | Event ID | Severity | Source / Provider | Message |\n|---|---:|---|---|---|\n" + "\n".join(formatted)


def _windows_event_rows(log_output):
    try:
        payload = json.loads(log_output or "[]")
    except json.JSONDecodeError:
        return []
    if isinstance(payload, dict):
        payload = [payload]
    return [{str(key).lower(): value for key, value in item.items()} for item in payload if isinstance(item, dict)]


def _format_event_severity_sections(log_output):
    rows = _windows_event_rows(log_output)
    sections = []
    for severity in ("Critical", "Error", "Warning", "Information"):
        selected = [row for row in rows if str(row.get("leveldisplayname", "")).lower() == severity.lower()]
        payload = json.dumps(selected) if selected else ""
        sections.append(f"### {severity} events\n\n{_format_log_lines(payload, limit=10) if selected else f'No {severity.lower()} events were returned.'}")
    return "\n\n".join(sections)


def _format_event_count_table(count_output):
    try:
        counts = json.loads(count_output or "{}")
    except json.JSONDecodeError:
        counts = {}
    rows = "\n".join(f"| {level} | {int(counts.get(level, 0) or 0)} |" for level in ("Critical", "Error", "Warning", "Information"))
    return "| Severity | Events in last 24 hours |\n|---|---:|\n" + rows


def _format_service_history(raw_output, service_name, limit=8):
    """Format service-control evidence without inventing an actor or reason."""
    try:
        events = json.loads(raw_output or "[]")
    except json.JSONDecodeError:
        events = []
    if isinstance(events, dict):
        events = [events]
    if not events:
        return (
            f"No {service_name} stop/start events were found in the last 24 hours. "
            "Who stopped it and why were not recorded in the available logs."
        )
    rows = []
    actor_found = False
    for event in events[:limit]:
        event_id = event.get("Id", "Unknown")
        timestamp = event.get("TimeCreated", "Unknown time")
        message = " ".join(str(event.get("Message") or "No message").split())
        user_id = event.get("UserId")
        actor = str(user_id) if user_id else "Not recorded"
        if user_id:
            actor_found = True
        rows.append(
            f"| {_table_cell(timestamp, 80)} | {_table_cell(event_id, 30)} | "
            f"`{_table_cell(actor, 80)}` | {_table_cell(message)} |"
        )
    conclusion = (
        "A recorded account/SID is shown above, but Service Control Manager events may run under SYSTEM; "
        "this does not always identify the person who requested the stop."
        if actor_found else
        "Windows recorded the service state change, but not who initiated it or the business reason. "
        "Enable Security process-creation auditing (Event 4688) and PowerShell logging for future attribution."
    )
    table = "| Time | Event ID | Recorded account/SID | Service action / message |\n|---|---:|---|---|\n" + "\n".join(rows)
    return table + f"\n\n**Attribution:** {conclusion}"


def _format_process_lines(process_output, limit=5):
    lines = [line.strip() for line in (process_output or "").splitlines() if line.strip()]
    lines = [line for line in lines if not set(line) <= {"-", " "}]
    if lines and any(word in lines[0].lower() for word in ("name", "user", "pid")):
        lines = lines[1:]
    return "\n".join(f"{index}. `{line}`" for index, line in enumerate(lines[:limit], start=1)) or "No process data returned."


def _format_uptime(uptime):
    text = " ".join((uptime or "N/A").split())
    values = {
        name.lower(): int(value)
        for name, value in re.findall(r"(?:^|\s)(Days|Hours|Minutes|Seconds)\s*:\s*(\d+)", text, re.I)
    }
    if values:
        return f"{values.get('days', 0)}d {values.get('hours', 0)}h {values.get('minutes', 0)}m"
    return text[:120]


def _base_summary_prefix(host, os_type, uptime, metrics):
    return (
        f"- **Server:** `{host}` ({os_type})\n"
        f"- **Remote connectivity:** ✅ Connected\n"
        f"- **Uptime:** {_format_uptime(uptime)}\n"
        f"- **Utilization:** Disk {_pct(metrics.get('disk_percent'))} | "
        f"Memory {_pct(metrics.get('memory_percent'))} | CPU {_pct(metrics.get('cpu_percent'))}\n\n"
    )


def _reboot_assessment(reboot_output):
    lowered = (reboot_output or "").lower()
    if re.search(r"\bid\s*:\s*1074\b", lowered):
        return "A planned shutdown or restart was recorded (Event ID 1074). Review the event message for the initiating process, account, and reason."
    if "kernel-power" in lowered or re.search(r"\bid\s*:\s*41\b", lowered) or re.search(r"\bid\s*:\s*6008\b", lowered):
        return "An unexpected shutdown, power interruption, or forced restart was recorded (Event ID 41 or 6008)."
    if re.search(r"\bid\s*:\s*6005\b", lowered) or re.search(r"\bid\s*:\s*6006\b", lowered):
        return "Windows Event Log start/stop activity was recorded (Event ID 6005/6006), but no definitive reboot initiator was identified."
    return "No relevant reboot or shutdown events were found in the available 24-hour history."


def _resource_action_guidance(resource):
    return (
        f"*Action requested:* Confirm whether this {resource.lower()} usage and the listed consumers are expected.\n"
        "• If normal with no performance impact, silence the alert or adjust its threshold.\n"
        "• If unexpected, investigate and reduce the listed consumers.\n"
        "• If expected but capacity is insufficient, increase the relevant VM resources."
    )


def _resource_conclusion(host, resource, current_value, process_output, os_type):
    key = "cpu_percent" if resource == "CPU" else "memory_percent"
    samples = metrics_history.load_recent(host, hours=3)
    history_values = [sample.get(key) for sample in samples]
    history_values = [float(value) for value in history_values if value is not None]
    average = sum(history_values) / len(history_values) if history_values else None
    threshold = config.APPLICATION_OWNER_UTILIZATION_THRESHOLD
    current_high = current_value is not None and float(current_value) > threshold
    sustained_high = average is not None and average > threshold
    rows = email_handler._process_rows(process_output, os_type, resource.lower())
    if rows:
        process_name, process_value = rows[0]
        unit = "MB" if resource == "Memory" and os_type == "windows" else (
            "CPU seconds" if resource == "CPU" and os_type == "windows" else "%"
        )
        consumer = f"`{process_name}` ({process_value:.2f} {unit})"
    else:
        consumer = "No process data was returned"

    current_text = "HIGH" if current_high else "NORMAL"
    history_text = (
        f"{average:.1f}% across {len(history_values)} observation(s) - {'HIGH' if sustained_high else 'NORMAL'}"
        if average is not None else "Insufficient observations in the last 3 hours"
    )
    if current_high and sustained_high:
        assessment = f"The {resource.lower()} condition appears sustained, not temporary. Investigate the top consumer and consider increasing capacity if the workload is expected."
    elif current_high:
        assessment = f"Current {resource.lower()} is high, but the available three-hour history does not confirm a sustained condition. Monitor and recheck before increasing capacity."
    elif sustained_high:
        assessment = f"Current {resource.lower()} is normal, but the three-hour average remains high. The spike may be recovering; continue monitoring."
    else:
        assessment = f"{resource} utilization is normal and the available history does not indicate sustained pressure. No immediate action is required."
    return (
        f"### {resource} conclusion\n\n"
        f"- **Current utilization:** {_pct(current_value)} - **{current_text}**\n"
        f"- **Observed three-hour average:** {history_text}\n"
        f"- **Top consumer:** {consumer}\n"
        f"- **Assessment:** {assessment}"
    )


def _upload_process_chart(slack_channel, thread_ts, host, os_type, resource, raw_output):
    if not slack_channel:
        return None
    rows = email_handler._process_rows(raw_output, os_type, resource.lower())
    if not rows:
        return {"ok": False, "error": "No process data was returned for the chart"}
    unit = ("MB" if resource == "Memory" else "CPU seconds") if os_type == "windows" else f"% {resource}"
    color = "#7c3aed" if resource == "Memory" else "#f59e0b"
    image_path = chart_generator.generate_ranked_chart(rows, host, resource, unit, color)
    return slack_handler.upload_image_to_slack(
        slack_channel, image_path, f"Top {resource}-consuming processes — {host}",
        initial_comment=f"📊 Top {resource.lower()} consumers for {host}", thread_ts=thread_ts,
    )


def _build_disk_question_summary(host, os_type, uptime, metrics, disk_scan):
    return (
        f"📊 DISK BREAKDOWN\n\n"
        f"{_base_summary_prefix(host, os_type, uptime, metrics)}"
        "Top folders consuming disk space:\n"
        f"{_format_disk_scan_lines(disk_scan)}\n\n"
        "Focused disk check only. No outage remediation was triggered."
    )


def _build_patch_question_summary(host, os_type, uptime, metrics, patch_info):
    recent = patch_info.get("installed_patches", [])[:3]
    recent_lines = "\n".join(
        f"| `{_table_cell(item.get('patch_id', 'Unknown'))}` | {_table_cell(item.get('date', 'Unknown'))} | "
        f"{_table_cell(item.get('description', 'Patch'))} |"
        for item in recent
    ) or "| N/A | N/A | No recent patch history found |"
    pending = patch_info.get("pending_updates", [])[:5]
    pending_lines = "\n".join(
        f"| {_table_cell(item.get('title', 'Unknown'))} | {_table_cell(item.get('severity', 'Unknown'))} | "
        f"{_table_cell(item.get('description', 'Update'))} |"
        for item in pending
    ) or "| N/A | N/A | No pending updates found |"
    if str(patch_info.get("windows_update_service_status", "")).lower() != "running":
        recommendation = "Windows Update service is not running. Ask the server administrator to review and start wuauserv before relying on patch results."
    elif patch_info.get("automatic_updates") == "Disabled":
        recommendation = "Automatic Updates are disabled. Confirm the approved patching method or enable the required update policy."
    elif patch_info.get("critical_pending", 0):
        recommendation = "Schedule an urgent maintenance window for critical updates."
    elif patch_info.get("important_pending", 0):
        recommendation = "Plan routine patching for the available important updates."
    else:
        recommendation = "No pending critical or important updates were found; the server is up to date."
    return (
        "🔒 PATCH VALIDATION\n\n"
        f"- **Target:** `{host}` ({os_type})\n"
        "- **Connectivity:** ✅ Connected\n\n"
        "### Patch and update configuration\n\n"
        "| Validation item | Result |\n|---|---|\n"
        f"| Last successful update | {_table_cell(patch_info.get('last_update_date', 'Unknown'))} |\n"
        f"| Critical updates pending | {patch_info.get('critical_pending', 0)} |\n"
        f"| Important updates pending | {patch_info.get('important_pending', 0)} |\n"
        f"| Automatic Updates | {_table_cell(patch_info.get('automatic_updates', 'Unknown'))} |\n"
        f"| Update policy | {_table_cell(patch_info.get('automatic_update_policy', 'Unknown'))} |\n"
        f"| Windows Update service | {_table_cell(patch_info.get('windows_update_service_status', 'N/A'))} |\n"
        f"| Service startup mode | {_table_cell(patch_info.get('windows_update_service_start_mode', 'N/A'))} |\n\n"
        "### Recently installed patches\n\n"
        "| Patch ID | Installed date | Description |\n|---|---|---|\n"
        f"{recent_lines}\n\n"
        "### Pending updates\n\n"
        "| Update | Severity | Description |\n|---|---|---|\n"
        f"{pending_lines}\n\n"
        "### Recommendation\n\n"
        f"{recommendation}"
    )


def _build_cpu_question_summary(host, os_type, uptime, metrics, process_output):
    return (
        "#### Top CPU-consuming processes\n\n"
        f"{_format_process_lines(process_output)}\n\n"
        f"{_resource_conclusion(host, 'CPU', metrics.get('cpu_percent'), process_output, os_type)}"
    )


def _build_memory_question_summary(host, os_type, uptime, metrics, process_output):
    return (
        "#### Top memory-consuming processes\n\n"
        f"{_format_process_lines(process_output)}\n\n"
        f"{_resource_conclusion(host, 'Memory', metrics.get('memory_percent'), process_output, os_type)}"
    )


def _build_reboot_summary(host, os_type, uptime, metrics, reboot_output, failed_output, logs_output,
                          event_count_output, issues):
    lowered = (reboot_output or "").lower()
    if "1074" in lowered:
        cause = "Planned restart/shutdown event detected (Windows Event ID 1074)."
    elif "6008" in lowered or "kernel-power" in lowered or re.search(r"\bid\s*:\s*41\b", lowered):
        cause = "Unexpected shutdown or power-loss event detected (Event ID 6008/41)."
    else:
        cause = "Reboot cause could not be confirmed from the available 24-hour event history."
    return (
        "📜 WINDOWS EVENT LOG AND REBOOT INVESTIGATION\n\n"
        f"- **Target:** `{host}` ({os_type})\n"
        "- **Connectivity:** ✅ Connected\n"
        f"- **Uptime:** {uptime or 'Unavailable'}\n\n"
        f"### Event totals - last 24 hours\n\n{_format_event_count_table(event_count_output)}\n\n"
        f"{_format_event_severity_sections(logs_output)}\n\n"
        f"### Reboot and shutdown assessment\n\n- {cause}\n\n"
        f"{_format_log_lines(reboot_output, limit=10)}\n\n"
        "### Conclusion\n\n"
        "The investigation reviewed Windows System events from the last 24 hours. "
        "If a restart or shutdown is listed above, the server team should confirm its owner and business reason."
    )


def _build_health_question_summary(host, os_type, uptime, metrics, failed_output, logs_output,
                                   monitoring_state, issues, monitoring_was_stopped=False,
                                   monitoring_action=None, monitoring_history_output="",
                                   reboot_output=""):
    status = "CONNECTED - NEEDS ATTENTION ⚠️" if issues else "UP AND HEALTHY ✅"
    issue_lines = "\n".join(f"- {item}" for item in issues) or "- No critical health issues detected."
    if monitoring_was_stopped:
        action_ok = bool((monitoring_action or {}).get("success"))
        remediation_text = (
            f"- **Initial state:** `{config.MONITORING_SERVICE_NAME}` was stopped.\n"
            f"- **Action taken:** OpsAgent executed `Start-Service -Name '{config.MONITORING_SERVICE_NAME}'`.\n"
            f"- **Final state:** `{(monitoring_action or {}).get('status_after', 'Unknown')}`.\n"
            f"- **Verification:** {'✅ Alloy started successfully and is now running.' if action_ok else '❌ Alloy could not be started; administrator action is required.'}"
        )
    else:
        remediation_text = f"- No Alloy remediation was required. The observed state was `{monitoring_state}`."
    if issues:
        conclusion = (
            "The server accepted the remote connection and is online, but the health findings above require review. "
            "Address only the identified critical conditions; ordinary stopped trigger-start Windows services do not indicate an outage."
        )
    elif monitoring_was_stopped and (monitoring_action or {}).get("success"):
        conclusion = (
            f"The server is up and running. OpsAgent found `{config.MONITORING_SERVICE_NAME}` stopped, started it successfully, "
            "and verified recovery. No further action is required."
        )
    else:
        conclusion = (
            "The server is up and running normally. Remote connectivity, Alloy, uptime, utilization, and critical health checks passed. "
            "No automated action was required, and no manual intervention is needed."
        )
    return (
        f"🩺 SERVER HEALTH CHECK — {status}\n\n"
        "### Connectivity and current state\n\n"
        f"{_base_summary_prefix(host, os_type, uptime, metrics)}"
        f"- **Monitoring service:** `{monitoring_state}`\n\n"
        f"### Health findings\n\n{issue_lines}\n\n"
        f"### Automated remediation\n\n{remediation_text}\n\n"
        f"### {config.MONITORING_SERVICE_NAME} stop/start evidence - last 24 hours\n\n"
        f"{_format_service_history(monitoring_history_output, config.MONITORING_SERVICE_NAME)}\n\n"
        f"### Observed stopped automatic services - informational\n\n{_format_service_lines(failed_output)}\n\n"
        f"### Recent system errors\n\n{_format_log_lines(logs_output)}\n\n"
        f"### Reboot and shutdown assessment\n\n- {_reboot_assessment(reboot_output)}\n\n"
        f"{_format_log_lines(reboot_output, limit=10)}\n\n"
        "### Conclusion\n\n"
        f"{conclusion}"
    )


def _build_logs_question_summary(host, os_type, uptime, metrics, logs_output,
                                 event_count_output="", reboot_output=""):
    return (
        "📜 WINDOWS EVENT LOG AND REBOOT INVESTIGATION\n\n"
        f"- **Target:** `{host}` ({os_type})\n"
        "- **Connectivity:** ✅ Connected\n\n"
        f"### Event totals - last 24 hours\n\n{_format_event_count_table(event_count_output)}\n\n"
        f"{_format_event_severity_sections(logs_output)}\n\n"
        f"### Reboot and shutdown assessment\n\n- {_reboot_assessment(reboot_output)}\n\n"
        f"{_format_log_lines(reboot_output, limit=10)}"
    )


def _build_services_question_summary(host, os_type, uptime, metrics, failed_output):
    return (
        "🛠️ SERVICE STATUS\n\n"
        f"{_base_summary_prefix(host, os_type, uptime, metrics)}"
        "Failed services:\n\n"
        f"{_format_service_lines(failed_output)}\n\n"
        "Focused service check only. No monitoring remediation was triggered."
    )


def _build_monitoring_question_summary(host, os_type, uptime, metrics, monitoring_state):
    return (
        "📡 MONITORING STATUS\n\n"
        f"{_base_summary_prefix(host, os_type, uptime, metrics)}"
        f"Monitoring service `{config.MONITORING_SERVICE_NAME}` state: {monitoring_state}\n\n"
        "Focused monitoring check completed. Alloy is changed only when it exists and is stopped."
    )


def _build_summary_question_summary(host, os_type, uptime, metrics, patch_info, failed_output,
                                    logs_output, reboot_output, monitoring_state, diagnostics_data):
    health_findings = diagnostics.health_issues(diagnostics_data)
    critical_service_issue = next((item for item in health_findings if "critical services" in item.lower()), None)
    services_summary = critical_service_issue or "No configured critical services are stopped"
    os_version = diagnostics.os_version_summary(
        diagnostics_data.get("os_version", {}).get("stdout", ""), os_type
    )
    health = "Healthy" if not health_findings else "; ".join(health_findings)
    return (
        "🧾 FULL SERVER OVERVIEW A–Z\n\n"
        f"Operating system: {os_version}\n"
        f"{_base_summary_prefix(host, os_type, uptime, metrics)}"
        f"Patch status: last updated {patch_info.get('last_update_date', 'Unknown')} | "
        f"critical pending {patch_info.get('critical_pending', 0)} | important pending {patch_info.get('important_pending', 0)}\n"
        f"Services: {services_summary}\n"
        f"Monitoring service ({config.MONITORING_SERVICE_NAME}): {monitoring_state}\n"
        f"Overall health: {health}\n\n"
        f"Recent error-log highlights:\n\n{_format_log_lines(logs_output)}\n\n"
        f"Recent reboot/shutdown evidence:\n\n{_format_log_lines(reboot_output, limit=5)}\n\n"
        "Read-only A–Z overview completed. No remediation was triggered."
    )


def _focused_result(host, os_type, start_time, before, diagnosis, disk_scan=None):
    return {
        "host": host,
        "os_type": os_type,
        "start_time": start_time,
        "end_time": datetime.now(timezone.utc),
        "diagnostics_before": before,
        "diagnostics_after": before,
        "agent_result": {
            "diagnosis": diagnosis,
            "actions_taken": [],
            "resolved": True,
            "error": None,
        },
        "verdict": report.HEALTHY_FALSE_ALERT,
        "issues": [],
        "monitoring_was_stopped": False,
        "monitoring_service_state": "skipped",
        "disk_scan": disk_scan or [],
        "disk_chart_uploaded": False,
        "request_mode": "focused",
        "server_inventory": before.get("server_inventory"),
    }


def _help_message():
    return (
        "I'm Ops agent and I'm here to help.\n\n"
        "I can help with:\n"
        "• Server health investigation\n"
        "• Disk usage and top space-consuming folders\n"
        "• Patch status and pending updates\n"
        "• CPU, memory, failed services, and log checks\n"
        "• Monitoring service checks\n"
        "• Guarded AWS start, stop, and reboot requests\n\n"
        "Send a server name or IP address, or paste the full alert message.\n"
        "Examples:\n"
        "• `@Ops agent check server 44.200.233.80`\n"
        "• `@Ops agent can you check disk usage on 44.200.233.80`\n"
        "• `@Ops agent show patch status for 44.200.233.80`\n"
        "• `@Ops agent server prod-01 is down`\n"
        "• `@Ops agent start AWS-MS-OPSTESTVM` (creates an approval request; it does not start directly)\n"
        "• Authorized approver replies: `APPROVE SLK-XXXXXXXX`"
    )


def detect_request_mode(text):
    """Public wrapper so Streamlit and Slack use the same question routing."""
    return _detect_request_mode(text)


def _grafana_public_target(alert_text):
    """Read an explicitly labelled public endpoint without selecting private instance labels."""
    match = re.search(
        r"(?mi)^\s*-?\s*(?:public_ip|public_ipv4|target_public_ip)\s*=\s*([0-9]{1,3}(?:\.[0-9]{1,3}){3})\s*$",
        alert_text or "",
    )
    if not match:
        return None
    candidate = match.group(1)
    try:
        import ipaddress
        address = ipaddress.ip_address(candidate)
        return candidate if address.version == 4 and not address.is_private else None
    except ValueError:
        return None


def investigate(alert_text, host=None, os_preference=None, on_update=None, slack_channel=None,
                slack_thread_ts=None, request_mode="incident", requester="Unknown",
                ticket_ref=""):
    """Investigate one host; used by both Slack and Streamlit."""
    update = on_update or (lambda _message: None)
    extracted_host = host or agent.extract_server_address(alert_text, None)
    inventory_record = server_inventory.retrieve_for_alert(alert_text, extracted_host=extracted_host)
    decommission_record = None
    inventory_state = str((inventory_record or {}).get("status") or "unknown").lower()
    if inventory_record and inventory_state in decommission_inventory.OFF_STATES:
        decommission_record = decommission_inventory.register_from_server(inventory_record, requester=requester)
    elif not inventory_record:
        decommission_record = decommission_inventory.retrieve_for_alert(alert_text, extracted_host=extracted_host)
    # Once a unique inventory record is established, its canonical IP is the
    # execution target. Similarity search alone is never allowed to pick among
    # multiple records (see retrieve_for_alert).
    host = (inventory_record or {}).get("ip_address") or extracted_host or config.EC2_HOST
    profile = config.connection_profile(host, os_preference=os_preference, inventory_record=inventory_record)
    os_preference = (os_preference or profile["os_type"]).lower()
    monitoring_service = (inventory_record or {}).get("monitoring_service") or config.MONITORING_SERVICE_NAME
    important_services = (inventory_record or {}).get("important_services") or config.CRITICAL_SERVICE_NAMES
    start_time = datetime.now(timezone.utc)
    if decommission_record:
        inventory_state = str(decommission_record.get("power_state") or "unknown")
        reference = decommission_record.get("ticket_reference") or ticket_ref or f"OPS-{start_time.strftime('%Y%m%d%H%M%S')}"
        owner = decommission_record.get("owner") or "Unknown"
        server_name = decommission_record.get("server_name") or (inventory_record or {}).get("server_name") or host
        lifecycle = decommission_record.get("lifecycle_state") or "scream_test"
        state_label = "powered off" if inventory_state in {"stopped", "off", "poweredoff", "powered off"} else inventory_state
        update(f"🗃️ Decommission Inventory matched: {server_name}")
        update(f"🛑 Power state: {state_label} | Lifecycle: {lifecycle}")
        update(f"👤 Requested by: {requester or 'Unknown'} | Owner: {owner}")
        update(f"🎫 Decommission ticket: {reference}")
        update("ℹ️ Investigation stopped at inventory validation; decommissioned and scream-test systems are not network-probed.")
        empty_diagnostics = {
            "os_type": os_preference,
            "metrics": {"disk_percent": None, "memory_percent": None, "cpu_percent": None},
            "patch_info": {},
            "server_inventory": inventory_record,
        }
        return {
            "host": host, "os_type": os_preference, "start_time": start_time,
            "end_time": datetime.now(timezone.utc),
            "diagnostics_before": empty_diagnostics,
            "diagnostics_after": empty_diagnostics,
            "agent_result": {
                "diagnosis": (
                    f"🛑 SERVER POWER STATE CONFIRMED\n\n"
                    f"Server: `{server_name}`\n"
                    f"Cloud state: `{inventory_state}`\n"
                    f"Lifecycle: `{lifecycle}`\n"
                    f"Owner: `{owner}`\n"
                    f"Requested by: `{requester or 'Unknown'}`\n"
                    f"Decommission ticket: `{reference}`\n"
                    f"Reason: `{decommission_record.get('reason') or 'Not recorded'}`\n"
                    f"Scream-test end: `{decommission_record.get('scream_test_ends_at') or 'Not applicable'}`\n\n"
                    "No connectivity test was attempted. Confirm the lifecycle record with the owner before requesting reactivation."
                ),
                "actions_taken": [], "resolved": False, "error": None,
            },
            "verdict": report.TRUE_ALERT,
            "issues": [f"Decommission inventory reports lifecycle={lifecycle}, power_state={inventory_state}"],
            "monitoring_was_stopped": False,
            "monitoring_service_state": "unavailable",
            "disk_scan": [], "disk_chart_uploaded": False,
            "request_mode": "inventory_power_state",
            "server_inventory": inventory_record,
            "decommission_inventory": decommission_record,
            "ticket_ref": reference,
        }
    ssh = ssh_handler.SSHHandler(
        host=host,
        username=profile["username"],
        key_path=profile["key_path"],
        port=profile["port"],
    )
    connection_name = "Windows remote connection" if os_preference == "windows" else "SSH"
    if inventory_record:
        update(
            f"📚 Inventory matched: {inventory_record['server_name']} | {inventory_record['vm_type']} | "
            f"{inventory_record['application']} | owner: {inventory_record['application_team']}"
        )
    else:
        update("⚠️ No inventory record matched; using configured connection defaults")
    update(f"🔍 Alert detected at {start_time.strftime('%H:%M:%S UTC')}. Connecting to {host}...")
    try:
        try:
            ssh.connect()
        except Exception as exc:
            update("❌ Remote connection failed — collecting network evidence from OpsAgent...")
            network = network_diagnostics.collect(
                host, gateway_ip=(inventory_record or {}).get("gateway_ip") or config.TARGET_GATEWAY_IP or None
            )
            error_text = str(exc)
            authentication_failure = "authentication failed" in error_text.lower()
            resolution_steps = network_diagnostics.resolution_guidance(error_text, network)
            gateway = network.get("gateway_ip") or "unavailable"
            update(f"📡 Target ping: {'reply received' if network['target_ping']['success'] else 'no reply'}")
            update(f"🧭 Traceroute completed to {network.get('resolved_ip') or host}")
            update(f"🌐 Gateway ping ({gateway}): {'reply received' if network['gateway_ping']['success'] else 'no reply'}")
            empty_diagnostics = {
                "os_type": os_preference,
                "metrics": {"disk_percent": None, "memory_percent": None, "cpu_percent": None},
                "patch_info": {},
            }
            return {
                "host": host, "os_type": os_preference, "start_time": start_time,
                "end_time": datetime.now(timezone.utc),
                "diagnostics_before": empty_diagnostics,
                "diagnostics_after": empty_diagnostics,
                "agent_result": {
                    "diagnosis": (
                        "The server responded to network checks, but SSH authentication failed. Verify the Windows username and authorized private key."
                        if authentication_failure and network["target_ping"]["success"]
                        else "The server is unreachable. SSH could not connect; network evidence was collected from the OpsAgent host."
                    ),
                    "actions_taken": [],
                },
                "verdict": report.TRUE_ALERT,
                "issues": [f"Remote connection failed: {exc}"],
                "monitoring_was_stopped": False,
                "monitoring_service_state": "unknown",
                "disk_scan": [], "disk_chart_uploaded": False,
                "request_mode": "network_failure",
                "connection_error": str(exc),
                "authentication_failure": authentication_failure,
                "resolution_steps": resolution_steps,
                "network_diagnostics": network,
                "server_inventory": inventory_record,
            }
        update(f"✅ {connection_name} established to {host}")
        os_type = os_detector.detect_server_os(host, ssh, os_preference)
        ssh.os_type = os_type
        early_monitoring_action = None
        early_monitoring_was_stopped = False
        if request_mode in {"health_query", "monitoring_query"}:
            update(f"🔎 Connection succeeded — checking monitoring service ({monitoring_service})...")
            _probe, early_monitoring_state = diagnostics.run_monitoring_service_check(
                ssh, os_type, monitoring_service=monitoring_service
            )
            update(f"📡 Monitoring service state: {early_monitoring_state}")
            early_monitoring_was_stopped = early_monitoring_state == "stopped"
            if early_monitoring_was_stopped:
                update(f"⚠️ {monitoring_service} is stopped — starting service...")
                early_monitoring_action = remediation.restart_monitoring_service(ssh, service_name=monitoring_service)
                if early_monitoring_action.get("success"):
                    update(f"✅ {monitoring_service} started and verified Running")
                else:
                    update(f"❌ Failed to start {monitoring_service}: {early_monitoring_action.get('error') or 'unknown error'}")
        before = diagnostics.run_full_diagnostics(
            ssh, os_type, monitoring_service=monitoring_service, important_services=important_services
        )
        before["server_inventory"] = inventory_record

        uptime = before["uptime"].get("stdout") or "N/A"
        if request_mode in {"incident", "health_query", "summary_query"}:
            update(f"✅ Uptime: {_format_uptime(uptime)}")
        metrics = before["metrics"]
        utilization_updates = {
            "cpu_query": f"📊 CPU utilization: {_pct(metrics['cpu_percent'])}",
            "memory_query": f"📊 Memory utilization: {_pct(metrics['memory_percent'])}",
            "disk_query": f"📊 Disk utilization: {_pct(metrics['disk_percent'])}",
        }
        update(utilization_updates.get(
            request_mode,
            f"📊 Utilization — Disk: {_pct(metrics['disk_percent'])} | Memory: {_pct(metrics['memory_percent'])} | CPU: {_pct(metrics['cpu_percent'])}",
        ))
        patch_info = before.get("patch_info") or {}
        if request_mode in {"incident", "patch_query", "summary_query"}:
            update(
                "🔒 Patch status — "
                f"Last updated: {patch_info.get('last_update_date', 'Unknown')} | "
                f"Critical pending: {patch_info.get('critical_pending', 0)} | "
                f"Important pending: {patch_info.get('important_pending', 0)}"
            )
        failed_output = before["failed_services"].get("stdout", "").strip()
        logs_output = before["recent_logs"].get("stdout", "")
        top_cpu_output = before["top_cpu_processes"].get("stdout", "")
        top_memory_output = before["top_memory_processes"].get("stdout", "")
        monitoring_service_state = diagnostics.monitoring_service_state(before, os_type)
        monitoring_history_output = before.get("monitoring_service_history", {}).get("stdout", "")
        event_count_output = before.get("event_log_counts", {}).get("stdout", "")
        reboot_output = before.get("reboot_history", {}).get("stdout", "")

        disk_scan = []
        disk_chart_uploaded = False
        disk_percent = metrics.get("disk_percent")
        is_grafana_firing = "[FIRING" in (alert_text or "").upper()
        should_scan_disk = (
            request_mode == "disk_query"
            and (not is_grafana_firing or (disk_percent is not None and disk_percent > config.APPLICATION_OWNER_UTILIZATION_THRESHOLD))
        ) or (
            request_mode == "incident" and disk_percent is not None and disk_percent > 80
        )
        if should_scan_disk:
            if request_mode == "disk_query":
                update("📊 Running focused disk usage scan...")
            else:
                update("📊 Disk utilization is high — scanning top folders...")
            disk_scan = diagnostics.run_disk_scan(ssh, os_type)
            if slack_channel and disk_scan:
                image_path = chart_generator.generate_disk_chart(disk_scan, host, os_type)
                upload = slack_handler.upload_image_to_slack(
                    slack_channel,
                    image_path,
                    f"Disk Space Usage — {host}",
                    initial_comment=f"📊 Disk space breakdown for {host}",
                    thread_ts=slack_thread_ts,
                )
                disk_chart_uploaded = bool(upload.get("ok"))
                if disk_chart_uploaded:
                    if disk_percent > 95:
                        update("🔴 CRITICAL: Disk almost full — chart uploaded")
                    else:
                        update("📊 Disk space chart uploaded above")
                else:
                    update(f"⚠️ Disk chart upload failed: {upload.get('error', 'unknown Slack API error')}. Text results are included below.")

        if request_mode == "disk_query":
            if slack_channel and not disk_scan and disk_percent is not None:
                rows = [("Disk used", disk_percent), ("Disk free", max(100 - disk_percent, 0))]
                image_path = chart_generator.generate_ranked_chart(rows, host, "Disk", "%", "#2563eb")
                upload = slack_handler.upload_image_to_slack(
                    slack_channel, image_path, f"Disk utilization — {host}",
                    initial_comment=f"📊 Disk utilization for {host}: {disk_percent:.1f}% used",
                    thread_ts=slack_thread_ts,
                )
                disk_chart_uploaded = bool(upload.get("ok"))
                update("📊 Disk utilization chart uploaded" if disk_chart_uploaded else f"⚠️ Disk chart unavailable: {upload.get('error')}")
            diagnosis = _build_disk_question_summary(host, os_type, uptime, metrics, disk_scan)
            focused = _focused_result(host, os_type, start_time, before, diagnosis, disk_scan=disk_scan)
            focused["disk_chart_uploaded"] = disk_chart_uploaded
            focused["request_mode"] = "disk_query"
            return focused

        if request_mode == "patch_query":
            diagnosis = _build_patch_question_summary(host, os_type, uptime, metrics, patch_info)
            focused = _focused_result(host, os_type, start_time, before, diagnosis, disk_scan=disk_scan)
            focused["request_mode"] = "patch_query"
            return focused

        if request_mode == "cpu_query":
            upload = _upload_process_chart(slack_channel, slack_thread_ts, host, os_type, "CPU", top_cpu_output)
            if upload:
                update("📊 CPU process chart uploaded" if upload.get("ok") else f"⚠️ CPU chart unavailable: {upload.get('error')}")
            diagnosis = _build_cpu_question_summary(host, os_type, uptime, metrics, top_cpu_output)
            focused = _focused_result(host, os_type, start_time, before, diagnosis, disk_scan=disk_scan)
            focused["request_mode"] = "cpu_query"
            return focused

        if request_mode == "memory_query":
            upload = _upload_process_chart(slack_channel, slack_thread_ts, host, os_type, "Memory", top_memory_output)
            if upload:
                update("📊 Memory process chart uploaded" if upload.get("ok") else f"⚠️ Memory chart unavailable: {upload.get('error')}")
            diagnosis = _build_memory_question_summary(host, os_type, uptime, metrics, top_memory_output)
            focused = _focused_result(host, os_type, start_time, before, diagnosis, disk_scan=disk_scan)
            focused["request_mode"] = "memory_query"
            return focused

        if request_mode == "reboot_query":
            reboot_findings = diagnostics.health_issues(before)
            diagnosis = _build_reboot_summary(
                host, os_type, uptime, metrics, reboot_output, failed_output, logs_output,
                event_count_output, reboot_findings
            )
            focused = _focused_result(host, os_type, start_time, before, diagnosis, disk_scan=disk_scan)
            focused["request_mode"] = "reboot_query"
            focused["issues"] = reboot_findings
            return focused

        if request_mode == "health_query":
            monitoring_action = early_monitoring_action
            monitoring_was_stopped = early_monitoring_was_stopped or monitoring_service_state == "stopped"
            if monitoring_was_stopped:
                if monitoring_action is None:
                    monitoring_action = remediation.restart_monitoring_service(ssh, service_name=monitoring_service)
                monitoring_service_state = "running" if monitoring_action.get("success") else "stopped"
            health_findings = diagnostics.health_issues(before)
            if monitoring_action and not monitoring_action.get("success"):
                health_findings.insert(0, f"Failed to start monitoring service {monitoring_service}")
            if monitoring_service_state not in {"running", "not_installed"}:
                health_findings.insert(0, f"Monitoring service is {monitoring_service_state}")
            diagnosis = _build_health_question_summary(
                host, os_type, uptime, metrics, failed_output, logs_output,
                monitoring_service_state, health_findings,
                monitoring_was_stopped=monitoring_was_stopped,
                monitoring_action=monitoring_action,
                monitoring_history_output=monitoring_history_output,
                reboot_output=reboot_output,
            )
            focused = _focused_result(host, os_type, start_time, before, diagnosis, disk_scan=disk_scan)
            focused["request_mode"] = "health_query"
            focused["issues"] = health_findings
            focused["verdict"] = report.TRUE_ALERT if health_findings else (
                report.MONITORING_FALSE_ALERT if monitoring_was_stopped and monitoring_service_state == "running"
                else report.HEALTHY_FALSE_ALERT
            )
            focused["monitoring_was_stopped"] = monitoring_was_stopped
            focused["monitoring_service_state"] = monitoring_service_state
            if monitoring_action:
                focused["agent_result"]["actions_taken"].append({
                    "tool": "restart_monitoring_service", "arguments": {}, "result": monitoring_action,
                })
            return focused

        if request_mode == "logs_query":
            diagnosis = _build_logs_question_summary(
                host, os_type, uptime, metrics, logs_output, event_count_output, reboot_output
            )
            focused = _focused_result(host, os_type, start_time, before, diagnosis, disk_scan=disk_scan)
            focused["request_mode"] = "logs_query"
            return focused

        if request_mode == "services_query":
            diagnosis = _build_services_question_summary(host, os_type, uptime, metrics, failed_output)
            focused = _focused_result(host, os_type, start_time, before, diagnosis, disk_scan=disk_scan)
            focused["request_mode"] = "services_query"
            return focused

        if request_mode == "monitoring_query":
            monitoring_action = early_monitoring_action
            monitoring_was_stopped = early_monitoring_was_stopped or monitoring_service_state == "stopped"
            if monitoring_was_stopped:
                if monitoring_action is None:
                    monitoring_action = remediation.restart_monitoring_service(ssh, service_name=monitoring_service)
                monitoring_service_state = "running" if monitoring_action.get("success") else "stopped"
            diagnosis = _build_monitoring_question_summary(host, os_type, uptime, metrics, monitoring_service_state)
            focused = _focused_result(host, os_type, start_time, before, diagnosis, disk_scan=disk_scan)
            focused["request_mode"] = "monitoring_query"
            focused["monitoring_was_stopped"] = monitoring_was_stopped
            focused["monitoring_service_state"] = monitoring_service_state
            if monitoring_action:
                focused["agent_result"]["actions_taken"].append({
                    "tool": "restart_monitoring_service", "arguments": {}, "result": monitoring_action,
                })
            return focused

        if request_mode == "summary_query":
            summary_findings = diagnostics.health_issues(before)
            diagnosis = _build_summary_question_summary(
                host, os_type, uptime, metrics, patch_info, failed_output, logs_output,
                reboot_output, monitoring_service_state, before,
            )
            focused = _focused_result(host, os_type, start_time, before, diagnosis, disk_scan=disk_scan)
            focused["request_mode"] = "summary_query"
            focused["issues"] = summary_findings
            focused["verdict"] = report.TRUE_ALERT if summary_findings else report.HEALTHY_FALSE_ALERT
            return focused

        if not failed_output or "0 loaded units listed" in failed_output:
            update("✅ Failed Services: No failed services")
        else:
            update(f"⚠️ Failed Services: {failed_output[:300]}")
        logs = logs_output.lower()
        if any(word in logs for word in ("error", "fail", "critical", "panic", "oom")):
            update("⚠️ Recent Logs: Errors detected")
        else:
            update("✅ Recent Logs: No errors found")

        update(f"🔎 Checking monitoring service ({monitoring_service})...")
        monitoring_was_stopped = monitoring_service_state == "stopped"
        monitoring_restart = None
        if monitoring_was_stopped:
            update("⚠️ Monitoring service STOPPED — attempting restart...")
            monitoring_restart = remediation.restart_monitoring_service(ssh, service_name=monitoring_service)
            if monitoring_restart.get("success"):
                update("✅ Monitoring service restarted successfully")
            else:
                update("❌ Monitoring service restart failed")
        elif monitoring_service_state == "not_installed":
            update(
                f"ℹ️ Monitoring service ({monitoring_service}) is not installed on this server"
            )
            update(f"🛠️ Suggested fix: {config.MONITORING_SERVICE_INSTALL_HINT}")
        elif monitoring_service_state == "running":
            update("✅ Monitoring service: Running")
        else:
            update("⚠️ Monitoring service state could not be confirmed")

        prompt = diagnostics.format_diagnostics_for_prompt(before)
        agent_result = agent.run_agent(
            ssh, prompt, alert_text,
            inventory_context=server_inventory.incident_context(inventory_record),
            monitoring_service=monitoring_service,
        )
        if monitoring_restart:
            agent_result.setdefault("actions_taken", []).insert(0, {
                "tool": "restart_monitoring_service", "arguments": {}, "result": monitoring_restart
            })
        after = diagnostics.run_full_diagnostics(
            ssh, os_type, monitoring_service=monitoring_service, important_services=important_services
        )
        after["server_inventory"] = inventory_record
        monitoring_service_state_after = diagnostics.monitoring_service_state(after, os_type)
        verdict, issues = report.classify_incident(
            before, after, agent_result, monitoring_was_stopped, monitoring_service_state_after
        )
        return {
            "host": host, "os_type": os_type, "start_time": start_time,
            "end_time": datetime.now(timezone.utc), "diagnostics_before": before,
            "diagnostics_after": after, "agent_result": agent_result,
            "verdict": verdict, "issues": issues,
            "monitoring_was_stopped": monitoring_was_stopped,
            "monitoring_service_state": monitoring_service_state_after,
            "disk_scan": disk_scan,
            "disk_chart_uploaded": disk_chart_uploaded,
            "request_mode": "incident",
            "server_inventory": inventory_record,
        }
    finally:
        ssh.close()


def process_alert(alert_text, channel, ts=None, requester="Unknown", ticket_ref=""):
    reply = lambda text, blocks=None: slack_handler.post_message(channel, text, blocks=blocks, thread_ts=ts)
    if not _incident_lock.acquire(blocking=False):
        reply("⏳ Already investigating an active incident. Please retry shortly.")
        return
    try:
        is_grafana_alert = (
            bool(re.search(r"(?mi)^\[FIRING(?:[:\]])", alert_text or ""))
            and "grafana_folder" in (alert_text or "").lower()
        )
        # Grafana's `instance` is a monitoring label/internal hostname. Use the
        # configured reachable Windows endpoint for the actual investigation.
        host = (
            (_grafana_public_target(alert_text) or config.SLACK_TARGET_HOST)
            if is_grafana_alert
            else agent.extract_server_address(alert_text, config.SLACK_TARGET_HOST)
        )
        if not host:
            reply(_missing_target_message())
            return
        request_mode = _detect_request_mode(alert_text)
        if request_mode != "incident":
            result = investigate(
                alert_text,
                host=host,
                on_update=reply,
                slack_channel=channel,
                slack_thread_ts=ts,
                request_mode=request_mode,
                requester=requester,
                ticket_ref=ticket_ref,
            )
            if result.get("request_mode") == "inventory_power_state":
                slack_handler.post_structured_report(channel, result["agent_result"]["diagnosis"], thread_ts=ts)
                return
            current_metrics = result["diagnostics_after"].get("metrics", {})
            metrics_history.record_sample(result["host"], result["os_type"], current_metrics)
            trend = _utilization_trend(result["host"], request_mode)
            if trend:
                reply(trend)
            if request_mode == "health_query":
                if result["verdict"] == report.MONITORING_FALSE_ALERT:
                    reply(f"✅ RECOVERED — Server `{result['host']}` is online. `{config.MONITORING_SERVICE_NAME}` was stopped and OpsAgent restored it successfully.")
                elif result["verdict"] == report.HEALTHY_FALSE_ALERT:
                    reply(f"✅ FALSE ALERT — Server `{result['host']}` is up and running normally. No automated or manual action is required.")
                else:
                    reply(f"⚠️ SERVER ONLINE — Server `{result['host']}` accepted the remote connection, but one or more critical findings require review.")
            elif request_mode == "summary_query":
                if result.get("issues"):
                    reply(f"⚠️ SERVER OVERVIEW — Needs attention: {'; '.join(result['issues'])}")
                else:
                    reply(f"✅ SERVER OVERVIEW — Server `{result['host']}` is healthy. No critical findings were detected.")
            slack_handler.post_structured_report(channel, result["agent_result"]["diagnosis"], thread_ts=ts)
            if request_mode == "reboot_query":
                reboot_email = email_handler.send_reboot_investigation_email(result, alert_text)
                if reboot_email.get("sent"):
                    reply(f"📧 Reboot investigation emailed to `{reboot_email['recipient']}` for administrative follow-up.")
                else:
                    reply(f"⚠️ Reboot email not sent: {reboot_email.get('reason') or reboot_email.get('error', 'unknown error')}.")
            if (
                is_grafana_alert
                and request_mode in {"cpu_query", "memory_query", "disk_query"}
                and schedule_utilization_recheck(result, alert_text, request_mode, channel=channel, thread_ts=ts)
            ):
                reply(
                    "⏱️ Utilization is above 75%. I will monitor it and recheck in 5 minutes. "
                    "The application/server teams will be emailed only if it remains high.",
                )
            return
        result = investigate(
            alert_text,
            host=host,
            on_update=reply,
            slack_channel=channel,
            slack_thread_ts=ts,
            requester=requester,
            ticket_ref=ticket_ref,
        )
        if result.get("request_mode") == "inventory_power_state":
            slack_handler.post_structured_report(channel, result["agent_result"]["diagnosis"], thread_ts=ts)
            return
        fallback, blocks = report.build_report_blocks(alert_text=alert_text, **result)
        reply(fallback, blocks=blocks)
        utilization_email = email_handler.send_utilization_alert_email(result, alert_text)
        if utilization_email.get("sent"):
            reply(f"📧 High-utilization alert emailed to `{utilization_email['recipient']}`.")
        if result["verdict"] == report.TRUE_ALERT:
            slack_handler.notify_oncall(channel, result["host"], result["issues"], result["agent_result"])
            email_status = utilization_email if utilization_email.get("breaches") else email_handler.send_incident_email(result, alert_text)
            if email_status.get("sent") and not utilization_email.get("breaches"):
                reply(
                    f"📧 Incident report emailed to `{email_status['recipient']}`.",
                )
    except Exception as exc:
        traceback.print_exc()
        host = locals().get("host") or config.SLACK_TARGET_HOST or "unknown target"
        message = f"🚨 HIGH PRIORITY — Server {host} is DOWN or unreachable\n\n<@{config.ONCALL_SLACK_USER}> — You are on-call. Please check this server immediately!\n\nStatus: Manual intervention required.\nError: {exc}"
        reply(message)
        slack_handler.notify_oncall(channel, host, [str(exc)], {"actions_taken": []})
    finally:
        _incident_lock.release()


def _alert_worker():
    while True:
        health_status.update("queue_worker", "healthy", f"Waiting; queued={_alert_queue.qsize()}")
        alert_text, channel, ts, alert_key, audit = _alert_queue.get()
        try:
            health_status.update("queue_worker", "busy", f"Investigating {alert_key}; queued={_alert_queue.qsize()}")
            alert_metrics.record("started", alert_key, _detect_request_mode(alert_text), ts, **audit)
            ticket_ref = f"OPS-{str(ts or alert_key).replace('.', '').replace(':', '-')[-14:]}"
            process_alert(alert_text, channel, ts, requester=audit.get("requester", "Unknown"), ticket_ref=ticket_ref)
            alert_metrics.record("processed", alert_key, _detect_request_mode(alert_text), ts, **audit)
        finally:
            with _alert_state_lock:
                _active_alert_keys.discard(alert_key)
                _completed_alert_times[alert_key] = time.monotonic()
            _alert_queue.task_done()
            health_status.update("queue_worker", "healthy", f"Completed {alert_key}; queued={_alert_queue.qsize()}")


def on_alert(alert_text, channel, ts, requester=None):
    """Queue alerts so multiple simultaneous Grafana alerts are all investigated."""
    global _alert_worker_started
    alert_key = slack_handler._grafana_alert_key(alert_text) or f"message:{ts}"
    request_mode = _detect_request_mode(alert_text)
    inventory_record = server_inventory.retrieve_for_alert(alert_text)
    extracted_target = agent.extract_server_address(alert_text, None)
    target_name = (inventory_record or {}).get("server_name") or extracted_target or "Unresolved"
    audit = {"requester": slack_handler.requester_label(requester),
             "target_name": target_name, "request_text": alert_text}
    alert_metrics.record("received", alert_key, request_mode, ts, **audit)
    mute_minutes = config.DISK_ALERT_MUTE_MINUTES if request_mode == "disk_query" else config.ALERT_DEDUP_MINUTES
    now = time.monotonic()
    with _alert_state_lock:
        cutoff = mute_minutes * 60
        recently_completed = now - _completed_alert_times.get(alert_key, -cutoff - 1) < cutoff
        if alert_key in _active_alert_keys:
            acknowledgement_sent = slack_handler.post_message(channel, "ℹ️ Repeated alert received — this alert is already queued or being investigated.", thread_ts=ts)
            if acknowledgement_sent:
                alert_metrics.record("acknowledged", alert_key, request_mode, ts, **audit)
            alert_metrics.record("suppressed", alert_key, request_mode, ts, **audit)
            return
        if recently_completed:
            label = "Disk alert locally muted" if request_mode == "disk_query" else "Repeated alert suppressed"
            acknowledgement_sent = slack_handler.post_message(channel, f"ℹ️ {label} — an investigation completed within the last {mute_minutes} minutes.", thread_ts=ts)
            if acknowledgement_sent:
                alert_metrics.record("acknowledged", alert_key, request_mode, ts, **audit)
            alert_metrics.record("suppressed", alert_key, request_mode, ts, **audit)
            return
        _active_alert_keys.add(alert_key)
        position = len(_active_alert_keys)
    with _alert_worker_lock:
        if not _alert_worker_started:
            threading.Thread(target=_alert_worker, name="ops-alert-worker", daemon=True).start()
            _alert_worker_started = True
    if position > 1:
        acknowledgement_sent = slack_handler.post_message(channel, f"⏳ Alert queued at position {position}. The current investigation will finish first.", thread_ts=ts)
    else:
        acknowledgement_sent = slack_handler.post_message(channel, f"✅ Request acknowledged — investigating `{target_name}` now.", thread_ts=ts)
    if acknowledgement_sent:
        alert_metrics.record("acknowledged", alert_key, request_mode, ts, **audit)
    _alert_queue.put((alert_text, channel, ts, alert_key, audit))


def on_mention(_text, channel, ts):
    slack_handler.post_message(channel, _help_message())


def on_slack_action(text, channel, ts, requester, *, thread_ts=None, mentioned=False):
    return slack_actions.handle_message(
        text, channel, ts, requester, thread_ts=thread_ts, mentioned=mentioned
    )


def main():
    config.validate()
    import aws_inventory
    aws_inventory.start()
    print("OpsAgent AI starting...")
    print(f"Dashboard default target: {config.EC2_HOST}")
    print(f"Slack default target: {config.SLACK_TARGET_HOST}")
    slack_handler.register_alert_listener(
        on_alert, on_mention=on_mention, on_action=on_slack_action,
        action_recovery=slack_actions.recover_pending_thread_approvals,
    )
    inbound_email.start()
    slack_handler.start()


if __name__ == "__main__":
    main()

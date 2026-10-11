"""Optional SMTP notifications for application owners."""

import smtplib
import ssl
import html
from email.message import EmailMessage

import config
import chart_generator
import health_status
import retry_policy
import ops_log


def _recipients():
    return list(dict.fromkeys(filter(None, (config.APPLICATION_OWNER_EMAIL, config.SERVER_TEAM_EMAIL))))


def _source_platform(alert_text):
    text = (alert_text or "").lower()
    return "Slack / Grafana alert" if "[firing" in text or "grafana_folder" in text else "Streamlit dashboard"


def _disk_lines(disk_scan):
    rows = []
    for item in (disk_scan or [])[:10]:
        rows.append(f"- {item.get('folder', 'unknown')}: {float(item.get('size_gb', 0) or 0):.2f} GB")
    return "\n".join(rows) or "No folder-level disk scan was required or available."


def _process_rows(raw_output, os_type, resource):
    """Parse the existing Windows/Linux top-process diagnostic output."""
    rows = []
    for line in (raw_output or "").splitlines():
        line = line.strip()
        if not line or set(line) <= {"-", " "} or line.lower().startswith(("name ", "user ")):
            continue
        parts = line.rsplit(None, 2) if os_type == "windows" else line.split(None, 10)
        try:
            if os_type == "windows" and len(parts) == 3 and parts[1].isdigit():
                rows.append((f"{parts[0]} (PID {parts[1]})", float(parts[2])))
            elif os_type != "windows" and len(parts) >= 11 and parts[1].isdigit():
                index = 3 if resource == "memory" else 2
                rows.append((f"{parts[10]} (PID {parts[1]})", float(parts[index])))
        except ValueError:
            continue
    return rows[:5]


def _ranked_lines(rows, unit):
    return "\n".join(f"{index}. {name}: {value:.2f} {unit}" for index, (name, value) in enumerate(rows, 1)) or "No process data was returned."


def _owner_action_text(names):
    resources = names.lower()
    return (
        f"Action requested from the application/server owner:\n"
        f"A2Z Ops_Agent received a high {resources} utilization alert and identified the top consumers listed above. "
        "Please confirm whether this utilization and these processes are expected for the application.\n\n"
        "- If this is normal and has no performance impact, confirm that the alert can be silenced or its threshold adjusted.\n"
        "- If this is unexpected, investigate the listed processes and reduce their resource usage.\n"
        "- If the workload is expected but the server does not have enough capacity, confirm whether CPU, memory, or disk resources should be increased.\n\n"
        "Please reply with the preferred action so the operations team can proceed."
    )


def utilization_breaches(result):
    """Return metrics strictly above the application-owner alert threshold."""
    metrics = (result.get("diagnostics_after") or {}).get("metrics", {})
    threshold = config.APPLICATION_OWNER_UTILIZATION_THRESHOLD
    breaches = []
    for label, key in (("Disk", "disk_percent"), ("Memory", "memory_percent"), ("CPU", "cpu_percent")):
        value = metrics.get(key)
        if value is not None and float(value) > threshold:
            breaches.append((label, float(value)))
    return breaches


def _send(message):
    recipients = _recipients()
    subject = str(message.get("Subject", ""))[:200]
    ops_log.write("smtp", "INFO", "send_started",
                  f"Subject={subject!r}; configured recipients={len(recipients)}")
    try:
        def deliver():
            with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=20) as server:
                if config.SMTP_USE_TLS:
                    server.starttls(context=ssl.create_default_context())
                if config.SMTP_USERNAME:
                    server.login(config.SMTP_USERNAME, config.SMTP_PASSWORD)
                server.send_message(message)
        retry_policy.run(deliver, attempts=config.RETRY_ATTEMPTS, delay=config.RETRY_DELAY_SECONDS)
        health_status.update("smtp", "healthy", f"Last email sent to {len(recipients)} recipient(s)")
        ops_log.write("smtp", "INFO", "send_succeeded", f"Subject={subject!r}")
        return {"sent": True, "skipped": False, "recipient": ", ".join(recipients)}
    except Exception as exc:
        health_status.update("smtp", "error", exc)
        ops_log.write("smtp", "ERROR", "send_failed", f"{type(exc).__name__}: {exc}")
        print(f"[email_handler] Failed to send email: {exc}")
        return {"sent": False, "skipped": False, "error": str(exc)}


def send_patch_pipeline_email(recipients, subject, body, cycle_id=""):
    """Send an SCCM patch lifecycle notification to explicit cycle recipients."""
    recipients = list(dict.fromkeys(str(value).strip() for value in (recipients or []) if str(value).strip()))
    if not recipients:
        return {"sent": False, "skipped": True, "reason": "No recipients configured"}
    if not config.SMTP_HOST or not config.SMTP_FROM_EMAIL:
        return {"sent": False, "skipped": True, "reason": "SMTP_HOST or SMTP_FROM_EMAIL is not configured"}
    message = EmailMessage()
    message["Subject"] = str(subject)[:200]
    message["From"] = config.SMTP_FROM_EMAIL
    message["To"] = ", ".join(recipients)
    message.set_content(str(body))
    ops_log.write("sccm_patch", "INFO", "notification_started",
                  f"cycle={cycle_id}; recipients={len(recipients)}", cycle_id)
    try:
        def deliver():
            with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=20) as server:
                if config.SMTP_USE_TLS:
                    server.starttls(context=ssl.create_default_context())
                if config.SMTP_USERNAME:
                    server.login(config.SMTP_USERNAME, config.SMTP_PASSWORD)
                server.send_message(message)
        retry_policy.run(deliver, attempts=config.RETRY_ATTEMPTS, delay=config.RETRY_DELAY_SECONDS)
        ops_log.write("sccm_patch", "INFO", "notification_sent",
                      f"cycle={cycle_id}; subject={subject!r}; recipients={len(recipients)}", cycle_id)
        return {"sent": True, "skipped": False, "recipients": recipients}
    except Exception as exc:
        ops_log.write("sccm_patch", "ERROR", "notification_failed",
                      f"cycle={cycle_id}; {type(exc).__name__}: {exc}", cycle_id)
        return {"sent": False, "skipped": False, "error": str(exc)}


def send_utilization_alert_email(result, alert_text):
    """Notify the application owner when disk, memory, or CPU exceeds the threshold."""
    breaches = utilization_breaches(result)
    if not breaches:
        return {"sent": False, "skipped": True, "reason": "No utilization threshold exceeded", "breaches": []}
    if not _recipients():
        return {"sent": False, "skipped": True, "reason": "No application/server team email is configured", "breaches": breaches}
    if not config.SMTP_HOST or not config.SMTP_FROM_EMAIL:
        return {"sent": False, "skipped": True, "reason": "SMTP_HOST or SMTP_FROM_EMAIL is not configured", "breaches": breaches}

    breach_text = "\n".join(f"- {label}: {value:.2f}%" for label, value in breaches)
    names = ", ".join(label for label, _value in breaches)
    source_platform = _source_platform(alert_text)
    owner_action = _owner_action_text(names)
    diagnostics = result.get("diagnostics_after") or {}
    os_type = result.get("os_type", "unknown")
    detail_sections = []
    charts = []
    breached_names = {label for label, _value in breaches}
    if "Memory" in breached_names:
        rows = _process_rows(diagnostics.get("top_memory_processes", {}).get("stdout", ""), os_type, "memory")
        unit = "MB" if os_type == "windows" else "% memory"
        detail_sections.append(f"Top memory-consuming processes:\n{_ranked_lines(rows, unit)}")
        if rows:
            charts.append(("memory_chart", "Top memory-consuming processes", chart_generator.build_ranked_chart_png(rows, result.get("host", "unknown"), "Top Memory-consuming Processes", unit, "#7c3aed")))
    if "CPU" in breached_names:
        rows = _process_rows(diagnostics.get("top_cpu_processes", {}).get("stdout", ""), os_type, "cpu")
        unit = "CPU seconds" if os_type == "windows" else "% CPU"
        detail_sections.append(f"Top CPU-consuming processes:\n{_ranked_lines(rows, unit)}")
        if rows:
            charts.append(("cpu_chart", "Top CPU-consuming processes", chart_generator.build_ranked_chart_png(rows, result.get("host", "unknown"), "Top CPU-consuming Processes", unit, "#f59e0b")))
    if "Disk" in breached_names:
        disk_rows = [(item.get("folder", "unknown"), float(item.get("size_gb", 0) or 0)) for item in (result.get("disk_scan") or [])[:10]]
        detail_sections.append(f"Largest disk-consuming folders:\n{_disk_lines(result.get('disk_scan'))}")
        if disk_rows:
            charts.append(("disk_chart", "Largest disk-consuming folders", chart_generator.build_ranked_chart_png(disk_rows, result.get("host", "unknown"), "Largest Disk-consuming Folders", "GB", "#2563eb")))
    details_text = "\n\n".join(detail_sections)
    message = EmailMessage()
    message["Subject"] = f"[A2Z Ops_Agent][{source_platform}] High {names} utilization: {result.get('host', 'unknown')}"
    message["From"] = config.SMTP_FROM_EMAIL
    message["To"] = ", ".join(_recipients())
    message.set_content(
        f"A2Z Ops_Agent detected utilization above {config.APPLICATION_OWNER_UTILIZATION_THRESHOLD:g}%.\n\n"
        f"Source platform: {source_platform}\n"
        f"Target: {result.get('host', 'unknown')} ({result.get('os_type', 'unknown')})\n"
        f"Investigation: {alert_text}\n\n"
        f"Threshold breaches:\n{breach_text}\n\n"
        f"{details_text}\n\n"
        f"{owner_action}"
    )
    if charts:
        chart_html = "".join(f"<h3>{html.escape(title)}</h3><img src=\"cid:{cid}\" style=\"max-width:900px;width:100%;height:auto\">" for cid, title, _data in charts)
        message.add_alternative(
            "<html><body>"
            f"<h2>A2Z Ops_Agent utilization alert</h2><p><b>Source platform:</b> {html.escape(source_platform)}</p>"
            f"<p><b>Target:</b> {html.escape(str(result.get('host', 'unknown')))} ({html.escape(os_type)})</p>"
            f"<p><b>Threshold:</b> {config.APPLICATION_OWNER_UTILIZATION_THRESHOLD:g}%</p>"
            f"<pre>{html.escape(breach_text)}</pre><pre>{html.escape(details_text)}</pre>{chart_html}"
            "<h3>Action requested from the application/server owner</h3>"
            f"<p>A2Z Ops_Agent received a high {html.escape(names.lower())} utilization alert and identified the top consumers above. "
            "Please confirm whether this utilization and these processes are expected for the application.</p>"
            "<ul>"
            "<li>If this is normal and has no performance impact, confirm that the alert can be silenced or its threshold adjusted.</li>"
            "<li>If this is unexpected, investigate the listed processes and reduce their resource usage.</li>"
            "<li>If the workload is expected but capacity is insufficient, confirm whether CPU, memory, or disk resources should be increased.</li>"
            "</ul><p><b>Please reply with the preferred action so the operations team can proceed.</b></p></body></html>",
            subtype="html",
        )
        html_part = message.get_payload()[-1]
        for cid, _title, data in charts:
            html_part.add_related(data, maintype="image", subtype="png", cid=f"<{cid}>", filename=f"{cid}.png")
    status = _send(message)
    status["breaches"] = breaches
    return status


def send_reboot_investigation_email(result, alert_text):
    """Send reboot cause evidence and post-reboot health to the operations owners."""
    if not _recipients():
        return {"sent": False, "skipped": True, "reason": "No application/server team email is configured"}
    if not config.SMTP_HOST or not config.SMTP_FROM_EMAIL:
        return {"sent": False, "skipped": True, "reason": "SMTP_HOST or SMTP_FROM_EMAIL is not configured"}
    metrics = (result.get("diagnostics_after") or {}).get("metrics", {})
    evidence = (result.get("diagnostics_after") or {}).get("reboot_history", {}).get("stdout", "")
    message = EmailMessage()
    source_platform = _source_platform(alert_text)
    message["Subject"] = f"[A2Z Ops_Agent][{source_platform}] Windows reboot investigation: {result.get('host', 'unknown')}"
    message["From"] = config.SMTP_FROM_EMAIL
    message["To"] = ", ".join(_recipients())
    message.set_content(
        f"A Windows reboot was detected and investigated.\n\n"
        f"Source platform: {source_platform}\n"
        f"Target: {result.get('host', 'unknown')} ({result.get('os_type', 'unknown')})\n"
        f"Alert: {alert_text}\n"
        f"Uptime: {(result.get('diagnostics_after') or {}).get('uptime', {}).get('stdout', 'N/A')}\n"
        f"Disk: {metrics.get('disk_percent', 'N/A')}%\n"
        f"Memory: {metrics.get('memory_percent', 'N/A')}%\n"
        f"CPU: {metrics.get('cpu_percent', 'N/A')}%\n\n"
        f"Post-reboot findings:\n{result.get('agent_result', {}).get('diagnosis', 'Not available')}\n\n"
        f"Windows reboot evidence:\n{evidence or 'No reboot evidence returned.'}\n\n"
        "Server/application administrators: confirm who initiated the reboot, the approved change/reason, and complete further investigation if it was unexpected."
    )
    return _send(message)


def send_incident_email(result, alert_text):
    """Email a genuine-incident summary; return status without breaking the incident flow."""
    if not config.APPLICATION_OWNER_EMAIL:
        return {"sent": False, "skipped": True, "reason": "APPLICATION_OWNER_EMAIL is not configured"}
    if not config.SMTP_HOST or not config.SMTP_FROM_EMAIL:
        return {"sent": False, "skipped": True, "reason": "SMTP_HOST or SMTP_FROM_EMAIL is not configured"}

    metrics = (result.get("diagnostics_after") or {}).get("metrics", {})
    actions = result.get("agent_result", {}).get("actions_taken", [])
    action_lines = "\n".join(
        f"- {action.get('tool', 'unknown')}: "
        f"{'successful' if action.get('result', {}).get('success') else 'failed'}"
        for action in actions
    ) or "- No automated remediation was performed."
    issues = "\n".join(f"- {issue}" for issue in (result.get("issues") or [])) or "- Unknown health issue"

    message = EmailMessage()
    source_platform = _source_platform(alert_text)
    message["Subject"] = f"[A2Z Ops_Agent][{source_platform}] VM incident detected: {result.get('host', 'unknown')}"
    message["From"] = config.SMTP_FROM_EMAIL
    message["To"] = config.APPLICATION_OWNER_EMAIL
    message.set_content(
        f"A2Z Ops_Agent detected a genuine VM incident.\n\n"
        f"Source platform: {source_platform}\n"
        f"Target: {result.get('host', 'unknown')} ({result.get('os_type', 'unknown')})\n"
        f"Alert: {alert_text}\n"
        f"Disk: {metrics.get('disk_percent', 'N/A')}%\n"
        f"Memory: {metrics.get('memory_percent', 'N/A')}%\n"
        f"CPU: {metrics.get('cpu_percent', 'N/A')}%\n\n"
        f"Issues:\n{issues}\n\n"
        f"AI diagnosis:\n{result.get('agent_result', {}).get('diagnosis', 'Not available')}\n\n"
        f"Automated actions:\n{action_lines}\n\n"
        f"Largest disk-consuming folders:\n{_disk_lines(result.get('disk_scan'))}\n\n"
        "Please review the incident and take any required application-level action."
    )

    return _send(message)

"""Three-way incident classification and Slack Block Kit reports."""

import config
import diagnostics

MONITORING_FALSE_ALERT = "monitoring_false_alert"
MONITORING_NOT_INSTALLED = "monitoring_not_installed"
HEALTHY_FALSE_ALERT = "healthy_false_alert"
TRUE_ALERT = "true_alert"
_MAX_BLOCK_CHARS = 2800


def classify_incident(before, after, agent_result, monitoring_was_stopped=False, monitoring_service_state=None):
    """Classify from measured post-remediation health, not LLM wording."""
    issues = diagnostics.health_issues(after)
    monitoring_state = monitoring_service_state or diagnostics.monitoring_service_state(after)
    monitoring_running = monitoring_state == "running"
    agent_error = agent_result.get("error")
    if monitoring_was_stopped and monitoring_running and not issues and not agent_error:
        return MONITORING_FALSE_ALERT, []
    if monitoring_state == "not_installed" and not issues and not agent_error:
        return MONITORING_NOT_INSTALLED, []
    if monitoring_running and not issues and not agent_error:
        return HEALTHY_FALSE_ALERT, []
    monitoring_name = after.get("monitoring_service_name") or config.MONITORING_SERVICE_NAME
    if monitoring_state == "not_installed":
        issues.insert(0, f"{monitoring_name} service is not installed on this server")
    elif not monitoring_running:
        issues.insert(0, f"{monitoring_name} service is not running")
    if agent_error:
        issues.append(f"Automated analysis failed: {agent_error}")
    return TRUE_ALERT, issues or ["Health checks did not return a safe, healthy state"]


def _action_text(actions):
    if not actions:
        return "No auto-remediation was attempted."
    lines = []
    for action in actions:
        ok = action.get("result", {}).get("success")
        lines.append(f"{'✅' if ok else '❌'} `{action.get('tool')}`")
    return "\n".join(lines)


def format_patch_report(patch_info):
    """Create a compact human-readable patch summary for Slack and Streamlit."""
    patch_info = patch_info or {}
    installed = patch_info.get("installed_patches", [])
    pending = patch_info.get("pending_updates", [])
    recent_lines = [
        f"✅ {item.get('patch_id', 'Unknown')} — {item.get('date', 'Unknown')} — {item.get('description', 'Patch')}"
        for item in installed[:3]
    ] or ["No recent patch history found"]
    recommendation = "Server is up to date ✅"
    if str(patch_info.get("windows_update_service_status", "")).lower() not in {"running", "n/a"}:
        recommendation = "Windows Update service is not running — review/start wuauserv"
    elif patch_info.get("automatic_updates") == "Disabled":
        recommendation = "Automatic Updates are disabled — confirm the approved patch policy"
    elif patch_info.get("critical_pending", 0) > 0:
        recommendation = "Schedule patching window — critical updates pending"
    elif patch_info.get("important_pending", 0) > 0:
        recommendation = "Updates available — plan routine patching"
    return (
        f"Last updated: {patch_info.get('last_update_date', 'Unknown')}\n\n"
        "Recent patches installed:\n"
        + "\n".join(recent_lines)
        + f"\n\n⚠️ Pending updates: {len(pending)}\n"
        + f"🔴 Critical: {patch_info.get('critical_pending', 0)}\n"
        + f"🟡 Important: {patch_info.get('important_pending', 0)}\n\n"
        + f"Automatic updates: {patch_info.get('automatic_updates', 'Unknown')}\n"
        + f"Update policy: {patch_info.get('automatic_update_policy', 'Unknown')}\n"
        + f"Windows Update service: {patch_info.get('windows_update_service_status', 'N/A')} "
        + f"(startup: {patch_info.get('windows_update_service_start_mode', 'N/A')})\n\n"
        + f"Recommendation: {recommendation}"
    )


def build_report_blocks(alert_text, host, start_time, end_time, diagnostics_before,
                        diagnostics_after, agent_result, verdict=None, issues=None,
                        monitoring_was_stopped=False, monitoring_service_state=None,
                        os_type=None, **_extra):
    access_failure = bool(_extra.get("authentication_failure"))
    network_evidence = _extra.get("network_diagnostics") or {}
    server_reachable = bool(network_evidence.get("target_ping", {}).get("success"))
    verdict = verdict or classify_incident(
        diagnostics_before, diagnostics_after, agent_result, monitoring_was_stopped,
        monitoring_service_state,
    )[0]
    issues = issues or []
    mention = f"<@{config.ONCALL_SLACK_USER}>"
    inventory = _extra.get("server_inventory") or diagnostics_after.get("server_inventory") or {}
    monitoring_name = diagnostics_after.get("monitoring_service_name") or inventory.get("monitoring_service") or config.MONITORING_SERVICE_NAME
    if verdict == MONITORING_FALSE_ALERT:
        header = "✅ FALSE ALERT — Monitoring service was down"
        summary = (
            f"*Root cause:* `{monitoring_name}` service was stopped\n"
            f"*Action taken:* Service restarted successfully\n"
            f"Server `{host}` is healthy and running normally."
        )
    elif verdict == MONITORING_NOT_INSTALLED:
        header = "ℹ️ MONITORING CONFIG ISSUE — Service not installed"
        summary = (
            f"*Root cause:* `{monitoring_name}` is not installed on this server\n"
            "*Impact:* The server itself is healthy; this was not a real outage\n"
            f"*Recommended fix:* {config.MONITORING_SERVICE_INSTALL_HINT}"
        )
    elif verdict == HEALTHY_FALSE_ALERT:
        header = "✅ FALSE ALERT — Server is up and running fine"
        summary = (
            "All checks passed: SSH ✅ Uptime ✅ Disk ✅ Memory ✅ CPU ✅\n"
            "No failed services ✅ No critical errors in logs ✅"
        )
    elif access_failure and server_reachable:
        header = f"⚠️ INVESTIGATION BLOCKED — Server {host} is reachable"
        summary = (
            "*Network status:* Server responds to ping\n"
            "*Problem:* SSH authentication failed\n"
            "*Action:* Verify the Windows username and matching authorized private key."
        )
    else:
        header = f"🚨 HIGH PRIORITY — Server {host} is DOWN"
        issue_text = "\n".join(f"• {item}" for item in issues)
        summary = (
            f"*Issue detected:*\n{issue_text}\n\n{mention} — You are on-call. "
            "Please check this server immediately!\n\n*Status:* Manual intervention required."
        )

    metrics = diagnostics_after.get("metrics", {})
    patch_info = diagnostics_after.get("patch_info") or {}
    metric_text = " | ".join(
        f"{name}: {metrics.get(key):.0f}%" if metrics.get(key) is not None else f"{name}: N/A"
        for name, key in (("Disk", "disk_percent"), ("Memory", "memory_percent"), ("CPU", "cpu_percent"))
    )
    diagnosis = (agent_result.get("diagnosis") or "No agent summary available")[:_MAX_BLOCK_CHARS]
    patch_report = format_patch_report(patch_info)[:_MAX_BLOCK_CHARS]
    os_version = diagnostics.os_version_summary(
        diagnostics_after.get("os_version", {}).get("stdout", ""), os_type or diagnostics_after.get("os_type", "linux")
    )
    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": header[:150]}},
        {"type": "section", "text": {"type": "mrkdwn", "text": summary[:_MAX_BLOCK_CHARS]}},
        {"type": "divider"},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*Target:* `{host}`\n*Operating system:* {os_version}\n*Alert:* {alert_text}\n*Duration:* {(end_time-start_time).total_seconds():.1f}s\n*Utilization:* {metric_text}"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*🔒 Patch Status:*\n{patch_report}"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*AI diagnosis:*\n{diagnosis}"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*Auto-remediation:*\n{_action_text(agent_result.get('actions_taken', []))}"}},
    ]
    if inventory:
        inventory_text = (
            f"*Inventory:* `{inventory.get('server_name', host)}` | {inventory.get('vm_type', 'unknown')} | "
            f"{inventory.get('environment', 'unknown')}\n"
            f"*Application:* {inventory.get('application', 'Unknown')} | "
            f"*Owner:* {inventory.get('application_team', 'Unknown')}\n"
            f"*Expected important services:* {', '.join(inventory.get('important_services') or []) or 'None configured'}"
        )
        blocks.insert(3, {"type": "section", "text": {"type": "mrkdwn", "text": inventory_text[:_MAX_BLOCK_CHARS]}})
    network = _extra.get("network_diagnostics")
    if network:
        evidence = []
        for label, key in (("Server ping", "target_ping"), ("Traceroute", "traceroute"), ("Gateway ping", "gateway_ping")):
            item = network.get(key, {})
            output = (item.get("stdout") or "No output returned").strip()
            evidence.append(f"*{label}* (`{item.get('command', 'not run')}`)\n```{output[:700]}```")
        guidance = _extra.get("resolution_steps") or []
        guidance_text = "\n".join(f"{index}. {step}" for index, step in enumerate(guidance, 1))
        blocks.extend([
            {"type": "divider"},
            {"type": "section", "text": {"type": "mrkdwn", "text": (
                f"*Network evidence*\nResolved IPv4: `{network.get('resolved_ip') or 'Unavailable'}` | "
                f"Configured subnet gateway: `{network.get('gateway_ip') or 'Unavailable'}`\n\n"
                + "\n\n".join(evidence)
            )[:_MAX_BLOCK_CHARS]}},
        ])
        if guidance_text:
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"*Recommended resolution*\n{guidance_text}"[:_MAX_BLOCK_CHARS]}})
    return header, blocks


def build_text_report(result, alert_text="Manual Streamlit investigation"):
    """Create a readable report for the Streamlit expander."""
    if result.get("request_mode") == "network_failure":
        network = result.get("network_diagnostics", {})
        sections = []
        for label, key in (("Server ping", "target_ping"), ("Traceroute", "traceroute"), ("Gateway ping", "gateway_ping")):
            item = network.get(key, {})
            sections.append(f"{label} ({item.get('command', 'not run')}):\n{item.get('stdout', 'No output')}")
        guidance = "\n".join(f"{index}. {step}" for index, step in enumerate(result.get("resolution_steps") or [], 1))
        return (
            f"Verdict: {TRUE_ALERT}\nTarget: {result['host']}\n"
            f"Resolved IPv4: {network.get('resolved_ip') or 'Unavailable'}\n"
            f"Configured subnet gateway: {network.get('gateway_ip') or 'Unavailable'}\n"
            f"Connection error: {result.get('connection_error', 'Unknown')}\n\n"
            + "\n\n".join(sections)
            + f"\n\nRecommended resolution:\n{guidance or 'Review network and SSH configuration.'}"
        )
    metrics = result["diagnostics_after"].get("metrics", {})
    os_version = diagnostics.os_version_summary(
        result["diagnostics_after"].get("os_version", {}).get("stdout", ""), result["os_type"]
    )
    request_mode = result.get("request_mode", "incident")
    patch_report = format_patch_report(result["diagnostics_after"].get("patch_info"))
    issues = result.get("issues") or ["None"]
    base = (
        f"Verdict: {result['verdict']}\nTarget: {result['host']} ({os_version})\n"
        f"Alert: {alert_text}\nDisk: {metrics.get('disk_percent')}%\n"
        f"Memory: {metrics.get('memory_percent')}%\nCPU: {metrics.get('cpu_percent')}%\n"
        f"Issues: {', '.join(issues)}\n\n"
    )
    if request_mode in {"incident", "patch_query", "summary_query"}:
        base += f"Patch status:\n{patch_report}\n\n"
    base += (
        f"AI diagnosis:\n{result['agent_result'].get('diagnosis', 'N/A')}\n\n"
        f"Actions:\n{_action_text(result['agent_result'].get('actions_taken', []))}"
    )
    return base

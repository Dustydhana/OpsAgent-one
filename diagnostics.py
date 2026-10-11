"""Read-only Linux and Windows diagnostics plus normalized health metrics."""

import json
import re
import shlex
from datetime import datetime, timezone

import config

LINUX_COMMANDS = {
    "os_version": "cat /etc/os-release 2>/dev/null || uname -a",
    "disk_usage": "df -h /",
    "memory_usage": "free -m",
    "cpu_usage": "top -bn1 | head -20",
    "top_cpu_processes": "ps aux --sort=-%cpu | head -6",
    "top_memory_processes": "ps aux --sort=-%mem | head -6",
    "uptime": "uptime",
    "failed_services": "systemctl list-units --state=failed --no-pager",
    "recent_logs": "tail -n 50 /var/log/syslog 2>/dev/null || tail -n 50 /var/log/messages 2>/dev/null",
    "reboot_history": "last -x reboot shutdown | head -10",
    "monitoring_service": None,
    "monitoring_service_history": None,
}

WINDOWS_COMMANDS = {
    "os_version": "Get-CimInstance Win32_OperatingSystem | Select-Object Caption,Version,BuildNumber,OSArchitecture | ConvertTo-Json -Compress",
    "disk_usage": "Get-PSDrive C | Select-Object Used,Free | ConvertTo-Json -Compress",
    "memory_usage": "Get-CimInstance Win32_OperatingSystem | Select-Object TotalVisibleMemorySize,FreePhysicalMemory | ConvertTo-Json -Compress",
    "cpu_usage": "Get-CimInstance Win32_Processor | Select-Object LoadPercentage | ConvertTo-Json -Compress",
    "top_cpu_processes": "Get-Process | Sort-Object CPU -Descending | Select-Object -First 5 Name,Id,CPU | Format-Table -AutoSize",
    "top_memory_processes": "Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First 5 Name,Id,@{Name='MemoryMB';Expression={[math]::Round($_.WorkingSet64/1MB,2)}} | Format-Table -AutoSize",
    "uptime": "(Get-Date) - (gcim Win32_OperatingSystem).LastBootUpTime",
    "failed_services": "Get-Service | Where-Object {$_.StartType -eq 'Automatic' -and $_.Status -ne 'Running'} | Select-Object Name,Status | Format-Table -AutoSize",
    "recent_logs": "$rows = foreach ($level in 1,2,3,4) { Get-WinEvent -FilterHashtable @{LogName='System'; Level=$level; StartTime=(Get-Date).AddHours(-24)} -ErrorAction SilentlyContinue | Select-Object -First 10 @{Name='TimeCreated';Expression={$_.TimeCreated.ToString('yyyy-MM-dd HH:mm:ss')}},Id,LevelDisplayName,ProviderName,Message }; $rows | ConvertTo-Json -Compress",
    "event_log_counts": "$events = Get-WinEvent -FilterHashtable @{LogName='System'; StartTime=(Get-Date).AddHours(-24)} -ErrorAction SilentlyContinue; [PSCustomObject]@{Critical=@($events | Where-Object Level -eq 1).Count; Error=@($events | Where-Object Level -eq 2).Count; Warning=@($events | Where-Object Level -eq 3).Count; Information=@($events | Where-Object Level -eq 4).Count} | ConvertTo-Json -Compress",
    "reboot_history": "Get-WinEvent -FilterHashtable @{LogName='System'; Id=41,1074,6005,6006,6008; StartTime=(Get-Date).AddHours(-24)} -ErrorAction SilentlyContinue | Select-Object -First 12 TimeCreated,Id,ProviderName,Message | Format-List",
    "monitoring_service": None,
    "monitoring_service_history": None,
}

LABELS = {
    "os_version": "Operating System Version",
    "disk_usage": "Disk Usage", "memory_usage": "Memory Usage", "cpu_usage": "CPU Usage",
    "top_cpu_processes": "Top CPU Processes", "top_memory_processes": "Top Memory Processes",
    "uptime": "Uptime", "failed_services": "Failed Services", "recent_logs": "Recent Logs", "reboot_history": "Reboot History",
    "monitoring_service": "Monitoring Service", "patch_info": "Patch Status",
    "monitoring_service_history": "Monitoring Service History",
    "event_log_counts": "Windows Event Counts",
}
MAX_CHARS_PER_SECTION = 2000


def _powershell(command):
    escaped = command.replace('"', '\\"')
    return f'powershell -NoProfile -NonInteractive -Command "{escaped}"'


def diagnostic_commands(os_type, monitoring_service=None, important_services=None):
    commands = dict(WINDOWS_COMMANDS if os_type == "windows" else LINUX_COMMANDS)
    service = monitoring_service or config.MONITORING_SERVICE_NAME
    if os_type == "windows":
        commands["monitoring_service"] = (
            f"$s = Get-Service -Name '{service}' -ErrorAction SilentlyContinue; "
            "if ($s) { [PSCustomObject]@{Name=$s.Name; Status=$s.Status.ToString()} | ConvertTo-Json -Compress }"
        )
        commands["monitoring_service_history"] = (
            f"$events = Get-WinEvent -FilterHashtable @{{LogName='System'; ProviderName='Service Control Manager'; "
            "Id=7035,7036,7040; StartTime=(Get-Date).AddHours(-24)}} -ErrorAction SilentlyContinue | "
            f"Where-Object {{$_.Message -match '{service}'}} | Select-Object -First 12 "
            "@{Name='TimeCreated';Expression={$_.TimeCreated.ToString('yyyy-MM-dd HH:mm:ss')}},"
            "Id,@{Name='UserId';Expression={if ($_.UserId) {$_.UserId.Value} else {$null}}},Message; "
            "$events | ConvertTo-Json -Compress"
        )
    else:
        commands["monitoring_service"] = f"systemctl is-active {service}"
        commands["monitoring_service_history"] = f"journalctl -u {service} --since '24 hours ago' --no-pager -n 30"
    important_services = [str(name).strip() for name in (important_services or []) if str(name).strip()]
    if important_services:
        if os_type == "windows":
            quoted = ",".join("'" + name.replace("'", "''") + "'" for name in important_services)
            commands["inventory_services"] = (
                f"Get-Service -Name {quoted} -ErrorAction SilentlyContinue | "
                "Select-Object Name,Status,StartType | ConvertTo-Json -Compress"
            )
        else:
            safe_names = " ".join(shlex.quote(name) for name in important_services)
            commands["inventory_services"] = (
                f"for svc in {safe_names}; do printf '%s=' \"$svc\"; "
                "systemctl is-active \"$svc\" 2>/dev/null || echo not-found; done"
            )
    return commands


def run_monitoring_service_check(ssh, os_type="linux", monitoring_service=None):
    """Run only the configured monitoring-service check and normalize its state."""
    command = diagnostic_commands(os_type, monitoring_service=monitoring_service)["monitoring_service"]
    result = ssh.run_command(_powershell(command) if os_type == "windows" else command)
    return result, monitoring_service_state({"os_type": os_type, "monitoring_service": result}, os_type)


def run_full_diagnostics(ssh, os_type="linux", monitoring_service=None, important_services=None):
    results = {
        "os_type": os_type,
        "monitoring_service_name": monitoring_service or config.MONITORING_SERVICE_NAME,
        "inventory_critical_services": list(important_services or []),
    }
    for key, command in diagnostic_commands(os_type, monitoring_service, important_services).items():
        results[key] = ssh.run_command(_powershell(command) if os_type == "windows" else command)
    results["patch_info"] = run_patch_check(ssh, os_type)
    results["collected_at"] = datetime.now(timezone.utc).isoformat()
    results["metrics"] = extract_metrics(results, os_type)
    return results


def _load_jsonish(text, fallback):
    if not text:
        return fallback
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return fallback


def os_version_summary(raw_output, os_type="linux"):
    """Return one concise OS edition/version/build string for reports."""
    if os_type == "windows":
        data = _load_jsonish(raw_output, {})
        if isinstance(data, dict):
            caption = str(data.get("Caption") or "Windows").strip()
            version = str(data.get("Version") or "").strip()
            build = str(data.get("BuildNumber") or "").strip()
            architecture = str(data.get("OSArchitecture") or "").strip()
            details = " · ".join(item for item in (f"Version {version}" if version else "", f"Build {build}" if build else "", architecture) if item)
            return f"{caption}{' · ' + details if details else ''}"
        return "Windows (version unavailable)"

    values = {}
    for line in (raw_output or "").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"')
    return values.get("PRETTY_NAME") or (raw_output or "Linux (version unavailable)").splitlines()[0]


def _linux_size_to_gb(size_text):
    match = re.match(r"(?i)^\s*([\d.]+)\s*([kmgtp]?)(?:i?b?)?\s*$", size_text or "")
    if not match:
        return None
    value = float(match.group(1))
    unit = match.group(2).upper()
    multipliers = {"": 1 / (1024 ** 3), "K": 1 / (1024 ** 2), "M": 1 / 1024, "G": 1, "T": 1024, "P": 1024 ** 2}
    return round(value * multipliers.get(unit, 0), 2)


def run_disk_scan(ssh, os_type="linux"):
    """Return the top folders by size as [{'folder': str, 'size_gb': float}, ...]."""
    if os_type == "windows":
        command = (
            "Get-ChildItem C:\\ -Directory -ErrorAction SilentlyContinue | "
            "ForEach-Object { "
            "$size = (Get-ChildItem $_.FullName -Recurse -ErrorAction SilentlyContinue | "
            "Measure-Object -Property Length -Sum).Sum; "
            "[PSCustomObject]@{Folder=$_.Name; SizeGB=[math]::Round(($size / 1GB), 2)} "
            "} | Sort-Object SizeGB -Descending | Select-Object -First 10 | ConvertTo-Json -Compress"
        )
        result = ssh.run_command(_powershell(command), timeout=120)
        payload = _load_jsonish(result.get("stdout"), [])
        if isinstance(payload, dict):
            payload = [payload]
        return [
            {"folder": str(item.get("Folder", "unknown")), "size_gb": float(item.get("SizeGB", 0) or 0)}
            for item in payload
            if isinstance(item, dict)
        ]

    result = ssh.run_command("du -sh /* 2>/dev/null | sort -rh | head -10", timeout=120)
    disk_rows = []
    for line in result.get("stdout", "").splitlines():
        match = re.match(r"^\s*(\S+)\s+(.+?)\s*$", line)
        if not match:
            continue
        size_gb = _linux_size_to_gb(match.group(1))
        if size_gb is None:
            continue
        disk_rows.append({"folder": match.group(2), "size_gb": size_gb})
    return disk_rows


def _first_number(pattern, text):
    match = re.search(pattern, text, re.I | re.M)
    return float(match.group(1)) if match else None


def _default_patch_info():
    return {
        "installed_patches": [],
        "pending_updates": [],
        "last_update_date": "Unknown",
        "critical_pending": 0,
        "important_pending": 0,
        "automatic_updates": "Unknown",
        "automatic_update_policy": "Unknown",
        "windows_update_service_status": "N/A",
        "windows_update_service_start_mode": "N/A",
    }


def _normalize_windows_date(value):
    """Normalize PowerShell DateTime strings and /Date(milliseconds)/ JSON objects."""
    if isinstance(value, dict):
        date_text = value.get("DateTime")
        if date_text:
            for fmt in ("%A, %B %d, %Y %I:%M:%S %p", "%A, %B %d, %Y %H:%M:%S"):
                try:
                    return datetime.strptime(date_text, fmt).strftime("%Y-%m-%d")
                except ValueError:
                    continue
        value = value.get("value") or value.get("Value") or ""
    text = str(value or "").strip()
    match = re.search(r"/Date\((\d+)(?:[+-]\d+)?\)/", text)
    if match:
        return datetime.fromtimestamp(int(match.group(1)) / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except ValueError:
        return text[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", text) else (text or "Unknown")


def _linux_package_manager(ssh):
    command = "command -v apt-get >/dev/null 2>&1 && echo apt || (command -v yum >/dev/null 2>&1 && echo yum) || (command -v dnf >/dev/null 2>&1 && echo dnf) || echo unknown"
    return (ssh.run_command(command, timeout=15).get("stdout") or "unknown").strip().lower()


def _parse_apt_installed(stdout):
    patches = []
    for line in stdout.splitlines():
        parts = line.split()
        if len(parts) < 6:
            continue
        patches.append({
            "patch_id": parts[3],
            "date": f"{parts[0]} {parts[1]} {parts[2]}",
            "description": " ".join(parts[4:]),
        })
    return patches


def _parse_apt_pending(stdout):
    updates = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("Inst "):
            continue
        parts = line.split()
        package = parts[1] if len(parts) > 1 else "unknown"
        severity = "Critical" if "security" in line.lower() else "Important"
        updates.append({"title": package, "severity": severity, "description": line})
    return updates


def _parse_rpm_installed(stdout):
    patches = []
    for line in stdout.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        patches.append({
            "patch_id": parts[0],
            "date": " ".join(parts[1:]),
            "description": parts[0],
        })
    return patches


def _parse_yum_pending(stdout):
    updates = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line or line.startswith(("Loaded plugins", "Obsoleting", "Security:", "Last metadata expiration")):
            continue
        if re.match(r"^[A-Za-z0-9_.:+-]+\s+[A-Za-z0-9_.:+-]+\s+\S+", line):
            package = line.split()[0]
            severity = "Critical" if "security" in line.lower() else "Important"
            updates.append({"title": package, "severity": severity, "description": line})
    return updates


def _parse_last_update_date(stdout, fallback="Unknown"):
    line = next((entry.strip() for entry in stdout.splitlines() if entry.strip()), "")
    if not line:
        return fallback
    parts = line.split()
    if len(parts) >= 8:
        return " ".join(parts[5:8])
    return line


def run_patch_check(ssh, os_type="linux"):
    """Collect recent patches, pending updates, and patch recency."""
    patch_info = _default_patch_info()
    if os_type == "windows":
        installed_cmd = (
            "Get-HotFix | Sort-Object InstalledOn -Descending | "
            "Select-Object HotFixID,Description,@{Name='InstalledOn';Expression={if ($_.InstalledOn) {$_.InstalledOn.ToString('yyyy-MM-dd')} else {'Unknown'}}} | "
            "Select-Object -First 5 | ConvertTo-Json -Compress"
        )
        pending_cmd = (
            "try { "
            "$s = New-Object -ComObject Microsoft.Update.Session; "
            "$r = $s.CreateUpdateSearcher().Search('IsInstalled=0'); "
            "$r.Updates | Select-Object Title,MsrcSeverity | ConvertTo-Json -Compress "
            "} catch { Write-Output '[]' }"
        )
        update_config_cmd = (
            "$svc = Get-CimInstance Win32_Service -Filter \"Name='wuauserv'\"; "
            "$au = Get-ItemProperty 'HKLM:\\SOFTWARE\\Policies\\Microsoft\\Windows\\WindowsUpdate\\AU' -ErrorAction SilentlyContinue; "
            "[PSCustomObject]@{ServiceStatus=$svc.State; StartMode=$svc.StartMode; "
            "NoAutoUpdate=$au.NoAutoUpdate; AUOptions=$au.AUOptions} | ConvertTo-Json -Compress"
        )
        installed_raw = ssh.run_command(_powershell(installed_cmd), timeout=60).get("stdout", "")
        pending_raw = ssh.run_command(_powershell(pending_cmd), timeout=60).get("stdout", "")
        update_config_raw = ssh.run_command(_powershell(update_config_cmd), timeout=30).get("stdout", "")
        installed = _load_jsonish(installed_raw, [])
        pending = _load_jsonish(pending_raw, [])
        if isinstance(installed, dict):
            installed = [installed]
        if isinstance(pending, dict):
            pending = [pending]
        patch_info["installed_patches"] = [
            {
                "patch_id": item.get("HotFixID", "Unknown"),
                "date": _normalize_windows_date(item.get("InstalledOn", "Unknown")),
                "description": item.get("Description", "Hotfix"),
            }
            for item in installed if isinstance(item, dict)
        ]
        patch_info["pending_updates"] = [
            {
                "title": item.get("Title", "Unknown"),
                "severity": item.get("MsrcSeverity") or "Important",
                "description": item.get("Title", "Unknown"),
            }
            for item in pending if isinstance(item, dict)
        ]
        if patch_info["installed_patches"]:
            patch_info["last_update_date"] = patch_info["installed_patches"][0]["date"]
        update_config = _load_jsonish(update_config_raw, {})
        if isinstance(update_config, dict):
            patch_info["windows_update_service_status"] = update_config.get("ServiceStatus") or "Unknown"
            patch_info["windows_update_service_start_mode"] = update_config.get("StartMode") or "Unknown"
            no_auto_update = update_config.get("NoAutoUpdate")
            patch_info["automatic_updates"] = "Disabled" if no_auto_update == 1 else "Enabled"
            policy_names = {
                2: "Notify before download/install",
                3: "Auto-download; notify before install",
                4: "Auto-download and scheduled install",
                5: "Local administrator chooses setting",
                7: "Notify to install and restart",
            }
            option = update_config.get("AUOptions")
            patch_info["automatic_update_policy"] = policy_names.get(option, "Windows default / not explicitly configured")
    else:
        package_manager = _linux_package_manager(ssh)
        if package_manager == "apt":
            installed_res = ssh.run_command("grep ' install ' /var/log/dpkg.log 2>/dev/null | tail -10", timeout=30)
            pending_res = ssh.run_command("apt-get -s upgrade 2>/dev/null | grep '^Inst' | head -10", timeout=45)
            last_update_res = ssh.run_command("ls -lt /var/cache/apt/pkgcache.bin 2>/dev/null | head -1", timeout=15)
            patch_info["installed_patches"] = _parse_apt_installed(installed_res.get("stdout", ""))
            patch_info["pending_updates"] = _parse_apt_pending(pending_res.get("stdout", ""))
            patch_info["last_update_date"] = _parse_last_update_date(last_update_res.get("stdout", ""), "Unknown")
        else:
            installed_res = ssh.run_command("rpm -qa --last 2>/dev/null | head -10", timeout=30)
            pending_res = ssh.run_command("yum check-update 2>/dev/null | tail -20", timeout=45)
            patch_info["installed_patches"] = _parse_rpm_installed(installed_res.get("stdout", ""))
            patch_info["pending_updates"] = _parse_yum_pending(pending_res.get("stdout", ""))
            if patch_info["installed_patches"]:
                patch_info["last_update_date"] = patch_info["installed_patches"][0]["date"]

    patch_info["critical_pending"] = sum(
        1 for item in patch_info["pending_updates"]
        if "critical" in str(item.get("severity", "")).lower() or "security" in str(item.get("severity", "")).lower()
    )
    patch_info["important_pending"] = max(len(patch_info["pending_updates"]) - patch_info["critical_pending"], 0)
    return patch_info


def extract_metrics(results, os_type=None):
    os_type = os_type or results.get("os_type", "linux")
    disk = results.get("disk_usage", {}).get("stdout", "")
    memory = results.get("memory_usage", {}).get("stdout", "")
    cpu = results.get("cpu_usage", {}).get("stdout", "")
    if os_type == "windows":
        used = _first_number(r'"Used"\s*:\s*(\d+)', disk)
        free = _first_number(r'"Free"\s*:\s*(\d+)', disk)
        total_mem = _first_number(r'"TotalVisibleMemorySize"\s*:\s*(\d+)', memory)
        free_mem = _first_number(r'"FreePhysicalMemory"\s*:\s*(\d+)', memory)
        disk_pct = used * 100 / (used + free) if used is not None and free is not None and used + free else None
        memory_pct = (total_mem - free_mem) * 100 / total_mem if total_mem and free_mem is not None else None
        cpu_pct = _first_number(r'"LoadPercentage"\s*:\s*(\d+)', cpu)
    else:
        disk_pct = _first_number(r'^\S+\s+\S+\s+\S+\s+\S+\s+(\d+)%', disk)
        mem_line = re.search(r'^Mem:\s+(\d+)\s+(\d+)', memory, re.M)
        memory_pct = (int(mem_line.group(2)) * 100 / int(mem_line.group(1))) if mem_line and int(mem_line.group(1)) else None
        idle = _first_number(r'(?:Cpu\(s\)|%Cpu\(s\)).*?([\d.]+)\s*id', cpu)
        cpu_pct = 100 - idle if idle is not None else None
    return {"disk_percent": disk_pct, "memory_percent": memory_pct, "cpu_percent": cpu_pct}


def monitoring_is_running(results, os_type=None):
    return monitoring_service_state(results, os_type) == "running"


def monitoring_service_state(results, os_type=None):
    os_type = os_type or results.get("os_type", "linux")
    item = results.get("monitoring_service", {})
    output = (item.get("stdout", "") or "").lower()
    error = (item.get("stderr", "") or "").lower()
    combined = f"{output}\n{error}".strip()
    if os_type == "windows":
        if item.get("success") and ("running" in output or bool(re.search(r'"status"\s*:\s*4\b', output))):
            return "running"
        if not combined or "cannot find any service" in combined:
            return "not_installed"
        if "stopped" in output or bool(re.search(r'"status"\s*:\s*1\b', output)):
            return "stopped"
        return "unknown"

    status = output.strip()
    if item.get("success") and status == "active":
        return "running"
    if (
        item.get("exit_code") == 4
        or "could not be found" in combined
        or "not-found" in combined
        or status in {"unknown", "not-found"}
    ):
        return "not_installed"
    if status in {"inactive", "failed", "activating", "deactivating"}:
        return "stopped"
    if status:
        return "unknown"
    return "stopped"


def health_issues(results, critical_services=None):
    critical_services = critical_services or results.get("inventory_critical_services") or config.CRITICAL_SERVICE_NAMES
    metrics = results.get("metrics") or extract_metrics(results)
    issues = []
    for name, threshold in (("disk", 90), ("memory", 90), ("cpu", 95)):
        value = metrics.get(f"{name}_percent")
        if value is not None and value >= threshold:
            issues.append(f"{name.title()} utilization is {value:.0f}%")
    failed = results.get("failed_services", {}).get("stdout", "").strip()
    if failed and "0 loaded units listed" not in failed:
        if results.get("os_type") == "windows":
            stopped_critical = [
                name for name in critical_services
                if re.search(rf"(?mi)^\s*{re.escape(name)}\s+stopped\s*$", failed)
            ]
            if stopped_critical:
                issues.append(f"Critical services not running: {', '.join(stopped_critical)}")
        elif "loaded units listed" not in failed:
            issues.append("One or more required services are not running")
    inventory_output = results.get("inventory_services", {}).get("stdout", "").lower()
    expected = [str(name).strip() for name in critical_services if str(name).strip()]
    stopped_inventory = []
    for name in expected:
        lowered = name.lower()
        if results.get("os_type") == "windows":
            if re.search(rf'(?i)"name"\s*:\s*"{re.escape(lowered)}"[^}}]*"status"\s*:\s*"(stopped|paused)', inventory_output):
                stopped_inventory.append(name)
        elif re.search(rf"(?mi)^{re.escape(lowered)}=(inactive|failed|not-found|unknown)\s*$", inventory_output):
            stopped_inventory.append(name)
    if stopped_inventory:
        issue = f"Inventory important services not running: {', '.join(stopped_inventory)}"
        if issue not in issues:
            issues.append(issue)
    logs = results.get("recent_logs", {}).get("stdout", "").lower()
    if any(word in logs for word in ("panic", "out of memory", "oom-killer", "critical")):
        issues.append("Critical errors found in recent system logs")
    return issues


def format_diagnostics_for_prompt(results):
    sections = []
    for key, label in LABELS.items():
        if key == "patch_info":
            patch_info = results.get("patch_info") or _default_patch_info()
            output = (
                f"Last update date: {patch_info.get('last_update_date', 'Unknown')}\n"
                f"Installed patches: {patch_info.get('installed_patches', [])}\n"
                f"Pending updates: {patch_info.get('pending_updates', [])}\n"
                f"Critical pending: {patch_info.get('critical_pending', 0)}\n"
                f"Important pending: {patch_info.get('important_pending', 0)}"
            )
        else:
            data = results.get(key, {})
            output = data.get("stdout") or "(no output)"
            if data.get("stderr"):
                output += f"\n[stderr]: {data['stderr']}"
        sections.append(f"### {label}\n```\n{output[:MAX_CHARS_PER_SECTION]}\n```")
    return "\n\n".join(sections)

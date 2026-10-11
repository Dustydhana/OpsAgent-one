"""
remediation.py
----------------
Concrete, narrowly-scoped auto-fix actions the agent is allowed to perform.

Design choice: the OpenAI agent NEVER generates raw shell commands to run.
It can only call these specific Python functions (exposed to it as "tools"
in agent.py). This keeps a human-auditable allowlist of every action the
agent can ever take on production infrastructure, and lets us validate every
argument before it touches a remote shell.

Every function here returns a JSON-serializable dict describing what
happened, and never raises - callers (the agent loop) always get a result
back, even on failure.
"""

import re
import shlex

import config

# Only allow safe characters in anything that gets interpolated into a
# remote shell command (service names, process names). Defense in depth on
# top of shlex.quote().
_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9_.@-]+$")


def _is_windows(ssh):
    return getattr(ssh, "os_type", "linux") == "windows"


def _powershell(command):
    return f'powershell -NoProfile -NonInteractive -Command "{command}"'


def clear_disk_space(ssh):
    """
    Free up disk space using a conservative set of cleanup operations:
    vacuum old systemd journal entries, delete stale /tmp files, remove
    rotated/compressed logs. Does not touch active, non-rotated logs.
    """
    if _is_windows(ssh):
        result = ssh.run_command(_powershell("Clear-RecycleBin -Force -ErrorAction SilentlyContinue"), timeout=60)
        return {"action": "clear_disk_space", "success": result["success"], "details": [result]}
    commands = [
        "sudo journalctl --vacuum-time=3d",
        "sudo find /tmp -type f -atime +2 -delete",
        "sudo find /var/log -name '*.gz' -delete",
        "sudo find /var/log -name '*.log.*' -mtime +7 -delete",
        "sudo apt-get clean -y",
    ]
    details = [ssh.run_command(cmd, timeout=60) for cmd in commands]
    df_after = ssh.run_command("df -h", timeout=15)

    return {
        "action": "clear_disk_space",
        "success": any(d["success"] for d in details),
        "details": details,
        "disk_after": df_after.get("stdout"),
    }


def restart_service(ssh, service_name):
    """Restart a single systemd service and report whether it is active afterward."""
    if not service_name or not _SAFE_NAME_RE.match(service_name):
        return {
            "action": "restart_service",
            "service": service_name,
            "success": False,
            "error": f"Rejected unsafe or empty service name: {service_name!r}",
        }

    safe_name = shlex.quote(service_name)
    if _is_windows(ssh):
        restart_res = ssh.run_command(_powershell(f"Restart-Service -Name '{service_name}' -Force"), timeout=30)
        status_res = ssh.run_command(_powershell(f"(Get-Service -Name '{service_name}').Status"), timeout=15)
    else:
        restart_res = ssh.run_command(f"sudo systemctl restart {safe_name}", timeout=30)
        status_res = ssh.run_command(f"systemctl is-active {safe_name}", timeout=15)

    return {
        "action": "restart_service",
        "service": service_name,
        "success": restart_res["exit_code"] == 0,
        "status_after": status_res.get("stdout"),
        "error": restart_res.get("stderr") or None,
    }


def restart_all_failed_services(ssh):
    """Look up every systemd unit currently in 'failed' state and restart each one."""
    if _is_windows(ssh):
        list_res = ssh.run_command(_powershell("Get-Service | Where-Object {$_.StartType -eq 'Automatic' -and $_.Status -ne 'Running'} | Select-Object -ExpandProperty Name"), timeout=15)
    else:
        list_res = ssh.run_command("systemctl list-units --state=failed --no-legend --plain", timeout=15)
    service_names = []
    for line in list_res.get("stdout", "").splitlines():
        parts = line.split()
        if parts:
            service_names.append(parts[0])

    results = [restart_service(ssh, name) for name in service_names]
    return {
        "action": "restart_all_failed_services",
        "services": service_names,
        "results": results,
        "success": all(r["success"] for r in results) if results else True,
    }


def restart_heavy_process(ssh, process_name=None, pid=None, reason=None):
    """
    Stop a runaway process identified by the agent as the cause of a
    memory/CPU spike. If it is managed by systemd it will typically be
    auto-restarted by systemd; otherwise this simply frees the resources.
    Exactly one of pid / process_name should be provided.
    """
    if pid is not None:
        try:
            pid_int = int(pid)
        except (TypeError, ValueError):
            return {
                "action": "restart_heavy_process",
                "success": False,
                "error": f"Invalid PID: {pid!r}",
            }
        command = _powershell(f"Stop-Process -Id {pid_int} -Force") if _is_windows(ssh) else f"sudo kill -9 {pid_int}"
        kill_res = ssh.run_command(command, timeout=15)
        return {
            "action": "restart_heavy_process",
            "pid": pid_int,
            "process": process_name,
            "reason": reason,
            "success": kill_res["exit_code"] == 0,
            "error": kill_res.get("stderr") or None,
        }

    if process_name and _SAFE_NAME_RE.match(process_name):
        safe_name = shlex.quote(process_name)
        command = _powershell(f"Stop-Process -Name '{process_name}' -Force") if _is_windows(ssh) else f"sudo pkill -9 -f {safe_name}"
        kill_res = ssh.run_command(command, timeout=15)
        # pkill exits 1 if no process matched - treat that as "already gone", not a failure.
        return {
            "action": "restart_heavy_process",
            "process": process_name,
            "reason": reason,
            "success": kill_res["exit_code"] in (0, 1),
            "error": kill_res.get("stderr") or None,
        }

    return {
        "action": "restart_heavy_process",
        "success": False,
        "error": "Must provide a valid 'pid' or 'process_name'.",
    }


def restart_monitoring_service(ssh, service_name=None):
    """Start the configured monitoring service and verify that it is running."""
    service_name = service_name or config.MONITORING_SERVICE_NAME
    if not service_name or not _SAFE_NAME_RE.match(service_name):
        return {
            "action": "restart_monitoring_service", "service": service_name,
            "success": False, "error": f"Rejected unsafe or empty service name: {service_name!r}",
        }

    if _is_windows(ssh):
        start_res = ssh.run_command(
            _powershell(f"Start-Service -Name '{service_name}' -ErrorAction Stop"), timeout=30
        )
        status_res = ssh.run_command(
            _powershell(f"(Get-Service -Name '{service_name}' -ErrorAction Stop).Status"), timeout=15
        )
        running = (status_res.get("stdout") or "").strip().lower() == "running"
    else:
        safe_name = shlex.quote(service_name)
        start_res = ssh.run_command(f"sudo systemctl start {safe_name}", timeout=30)
        status_res = ssh.run_command(f"systemctl is-active {safe_name}", timeout=15)
        running = (status_res.get("stdout") or "").strip().lower() == "active"

    return {
        "action": "restart_monitoring_service",
        "service": service_name,
        "success": start_res.get("exit_code") == 0 and running,
        "status_after": status_res.get("stdout"),
        "error": start_res.get("stderr") or status_res.get("stderr") or None,
    }

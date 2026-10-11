"""Operating-system detection for SSH-accessible target servers."""

import socket


def is_port_open(host, port, timeout=3):
    """Return True when a TCP connection can be established to host:port."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def detect_os(ssh):
    """Detect the remote OS using commands over an established SSH session."""
    uname = ssh.run_command("uname -s", timeout=10)
    if uname.get("success") and "linux" in uname.get("stdout", "").lower():
        return "linux"

    powershell = ssh.run_command(
        'powershell -NoProfile -NonInteractive -Command "[Environment]::OSVersion.Platform"',
        timeout=10,
    )
    if powershell.get("success") or "win32" in powershell.get("stdout", "").lower():
        return "windows"
    return "windows" if is_port_open(ssh.host, 3389) else "linux"


def detect_server_os(host, ssh=None, configured_os="auto"):
    """Return linux/windows, honoring an explicit configured OS override."""
    configured_os = (configured_os or "auto").lower()
    if configured_os in {"linux", "windows"}:
        return configured_os
    if ssh is not None and ssh.client is not None:
        return detect_os(ssh)
    if is_port_open(host, 22):
        return "linux"
    if is_port_open(host, 3389):
        return "windows"
    raise ConnectionError(f"Neither SSH (22) nor RDP (3389) is reachable on {host}.")

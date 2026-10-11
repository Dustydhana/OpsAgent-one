"""Controller-side network evidence for hosts that cannot accept SSH."""

import ipaddress
import platform
import shutil
import socket
import subprocess


def _run(command, timeout=30):
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout, check=False
        )
        output = (completed.stdout or completed.stderr or "No output returned.").strip()
        return {
            "command": " ".join(command),
            "stdout": output,
            "exit_code": completed.returncode,
            "success": completed.returncode == 0,
        }
    except subprocess.TimeoutExpired as exc:
        partial = exc.stdout or exc.stderr or ""
        if isinstance(partial, bytes):
            partial = partial.decode(errors="replace")
        output = partial.strip() or f"Command timed out after {timeout} seconds."
        return {
            "command": " ".join(command), "stdout": output,
            "exit_code": None, "success": False, "timed_out": True,
        }
    except OSError as exc:
        return {
            "command": " ".join(command),
            "stdout": str(exc),
            "exit_code": None,
            "success": False,
        }


def resolution_guidance(connection_error, network):
    """Return actionable help based on SSH and controller-side network evidence."""
    error = (connection_error or "").lower()
    ping_ok = bool((network.get("target_ping") or {}).get("success"))
    actions = []
    if "authentication failed" in error or "private key" in error or "key" in error:
        actions.extend([
            "The server is reachable, but login failed. Verify the selected OS username and matching private key.",
            "For Windows OpenSSH, confirm the public key is in the Administrator authorized_keys file with correct permissions.",
        ])
    elif "timed out" in error or "timeout" in error:
        actions.extend([
            "Confirm the EC2 instance is running and its public IP/DNS has not changed.",
            "Allow TCP port 22 from the OpsAgent source IP in the security group, network ACL, and Windows/Linux firewall.",
            "Confirm the subnet route and internet gateway permit return traffic.",
        ])
    elif "refused" in error:
        actions.extend([
            "The host is reachable but nothing accepted TCP port 22. Start the OpenSSH SSH Server service and set it to Automatic.",
            "Confirm sshd is listening on port 22 and the host firewall allows it.",
        ])
    elif "name or service" in error or "resolve" in error or "getaddrinfo" in error:
        actions.extend([
            "DNS resolution failed. Verify the hostname or use the current public IP address.",
            "Confirm the OpsAgent host can reach its configured DNS resolver.",
        ])
    else:
        actions.append("Verify instance state, IP address, TCP port 22, security-group rules, host firewall, username, and SSH key.")
    if ping_ok:
        actions.insert(0, "Ping succeeded, so the server is online; focus on SSH service, firewall, username, or key configuration.")
    else:
        actions.append("Ping can fail when ICMP is blocked; use the SSH error and traceroute together rather than ping alone.")
    if network.get("gateway_ip") and str(network.get("gateway_ip", "")).startswith(("10.", "172.", "192.168.")):
        actions.append("The configured gateway is private and is normally pingable only from inside the VPC/VPN; failure from a local laptop is expected.")
    return actions


def resolve_ipv4(host):
    """Return the first IPv4 address for an IP or hostname."""
    try:
        address = ipaddress.ip_address(host)
        return str(address) if address.version == 4 else None
    except ValueError:
        try:
            return next(
                item[4][0] for item in socket.getaddrinfo(host, None, socket.AF_INET)
            )
        except (OSError, StopIteration):
            return None


def gateway_with_last_octet_one(address):
    """Apply the requested gateway convention: replace the IPv4 last octet with 1."""
    if not address:
        return None
    try:
        ipv4 = ipaddress.IPv4Address(address)
    except ipaddress.AddressValueError:
        return None
    octets = str(ipv4).split(".")
    return ".".join(octets[:3] + ["1"])


def collect(host, gateway_ip=None):
    """Run ping, route trace, and derived-gateway ping from this agent host."""
    resolved_ip = resolve_ipv4(host)
    # A cloud public address is NAT and its `.1` neighbour is not the VM's
    # gateway. Only use `.1` for private addresses; otherwise require the real
    # gateway to be configured explicitly.
    if not gateway_ip and resolved_ip:
        try:
            if ipaddress.ip_address(resolved_ip).is_private:
                gateway_ip = gateway_with_last_octet_one(resolved_ip)
        except ValueError:
            gateway_ip = None
    windows = platform.system().lower() == "windows"
    ping_count = ["-n", "4"] if windows else ["-c", "4"]
    trace_program = "tracert" if windows else "traceroute"
    trace_args = ["-d", "-h", "15"] if windows else ["-n", "-m", "15"]

    target_ping = _run(["ping", *ping_count, resolved_ip or host], timeout=20)
    if shutil.which(trace_program):
        traceroute = _run([trace_program, *trace_args, resolved_ip or host], timeout=45)
    else:
        traceroute = {
            "command": f"{trace_program} {resolved_ip or host}",
            "stdout": f"{trace_program} is not installed on the OpsAgent host.",
            "exit_code": None,
            "success": False,
        }
    gateway_ping = (
        _run(["ping", *ping_count, gateway_ip], timeout=20)
        if gateway_ip
        else {
            "command": "ping <gateway unavailable>",
            "stdout": "Could not resolve the target to an IPv4 address.",
            "exit_code": None,
            "success": False,
        }
    )
    return {
        "target": host,
        "resolved_ip": resolved_ip,
        "gateway_ip": gateway_ip,
        "target_ping": target_ping,
        "traceroute": traceroute,
        "gateway_ping": gateway_ping,
    }

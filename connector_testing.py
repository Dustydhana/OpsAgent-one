"""Provider connection tests using decrypted tenant credentials in memory only."""

import imaplib
import smtplib

import vmware_operations


def test_slack(credentials: dict[str, str]) -> dict:
    from slack_sdk import WebClient
    token = credentials.get("bot_token", "")
    if not token:
        raise ValueError("Slack bot token is required")
    response = WebClient(token=token).auth_test()
    channels = [value.strip() for value in credentials.get("channels", "").split(",") if value.strip()]
    approvers = [value.strip() for value in credentials.get("approvers", "").split(",") if value.strip()]
    return {"connected": True, "provider": "slack", "team": response.get("team"),
            "bot_user_id": response.get("user_id"), "monitored_channels": len(channels),
            "approvers": len(approvers), "socket_mode": bool(credentials.get("app_token")),
            "incoming_webhook": bool(credentials.get("webhook_url"))}


def test_email(credentials: dict[str, str]) -> dict:
    username = credentials.get("username", "")
    password = credentials.get("app_password") or credentials.get("password", "")
    host = credentials.get("imap_host", "")
    if not (username and password and host):
        raise ValueError("Email address, app password and IMAP host are required")
    port = int(credentials.get("imap_port") or 993)
    with imaplib.IMAP4_SSL(host, port) as mailbox:
        mailbox.login(username, password)
        mailbox.select(credentials.get("imap_folder") or "INBOX", readonly=True)
        mailbox.logout()
    smtp_host = credentials.get("smtp_host", "")
    if smtp_host:
        with smtplib.SMTP(smtp_host, int(credentials.get("smtp_port") or 587), timeout=15) as sender:
            sender.starttls()
            sender.login(username, password)
    return {"connected": True, "provider": "gmail", "account": username, "imap_host": host}


def test_vmware(credentials: dict[str, str]) -> dict:
    endpoint = credentials.get("endpoint", "")
    client = vmware_operations.VMwareClient(
        endpoint=endpoint,
        username=credentials.get("username"),
        password=credentials.get("password"),
        port=int(credentials.get("port") or 443),
        verify_ssl=str(credentials.get("verify_ssl", "true")).lower() not in {"false", "0", "no"},
    )
    with client as session:
        environment = session.describe()
    vmware_operations.sync_inventory(environment)
    return {"connected": True, "provider": "vmware", "endpoint": endpoint,
            "product": environment.get("product"), "version": environment.get("version")}


def test_provider(provider: str, credentials: dict[str, str]) -> dict:
    if provider == "slack":
        return test_slack(credentials)
    if provider in {"gmail", "email", "outlook"}:
        return test_email(credentials)
    if provider == "vmware":
        return test_vmware(credentials)
    raise ValueError(f"Automated testing is not available for {provider}")

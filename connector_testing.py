"""Provider connection tests using decrypted tenant credentials in memory only."""

import imaplib
import smtplib

import vmware_operations


def test_slack(credentials: dict[str, str]) -> dict:
    from slack_sdk import WebClient
    token = credentials.get("bot_token", "")
    app_token = credentials.get("app_token", "")
    if not token or not app_token:
        raise ValueError("Slack bot token and Socket Mode app token are required")
    client = WebClient(token=token)
    response = client.auth_test()
    # auth.test only validates the bot token. Opening a Socket Mode URL also
    # verifies that the xapp token has connections:write and Socket Mode is on.
    WebClient(token=app_token).api_call("apps.connections.open")
    channels = [value.strip() for value in credentials.get("channels", "").split(",") if value.strip()]
    approvers = [value.strip() for value in credentials.get("approvers", "").split(",") if value.strip()]
    available = {}
    cursor = None
    while True:
        page = client.conversations_list(types="public_channel,private_channel", limit=200, cursor=cursor)
        for item in page.get("channels", []):
            available[item.get("id")] = item
            available[f"#{item.get('name')}"] = item
            available[item.get("name")] = item
        cursor = page.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break
    missing = [channel for channel in channels if channel not in available]
    not_joined = [channel for channel in channels if channel in available and not available[channel].get("is_member")]
    if missing:
        raise ValueError(f"Slack channel(s) not visible to the bot: {', '.join(missing)}")
    if not_joined:
        raise ValueError(f"Invite @Ops agent to: {', '.join(not_joined)}")
    return {"connected": True, "provider": "slack", "team": response.get("team"),
            "bot_user_id": response.get("user_id"), "monitored_channels": len(channels),
            "approvers": len(approvers), "socket_mode": True, "channel_membership": "verified",
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
    request_senders = [value.strip() for value in credentials.get("request_senders", "").split(",") if value.strip()]
    approvers = [value.strip() for value in credentials.get("approvers", "").split(",") if value.strip()]
    return {"connected": True, "provider": "gmail", "account": username, "imap_host": host,
            "folder": credentials.get("imap_folder") or "INBOX", "smtp_verified": bool(smtp_host),
            "authorized_senders": len(request_senders), "approvers": len(approvers),
            "processing_mode": "mailbox_verified"}


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

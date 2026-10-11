"""Safe, tenant-scoped connector configuration preflight.

Only boolean configuration state and operator guidance leave this module. Secret
values and credential references are deliberately never included in its output.
"""

import os

import integration_store


def _present(name: str) -> bool:
    return bool(os.getenv(name, "").strip())


def _check(key: str, label: str, configured: bool, guidance: str, required: bool = True) -> dict:
    return {
        "key": key,
        "label": label,
        "configured": configured,
        "required": required,
        "guidance": guidance,
    }


def _provider(provider_id: str, name: str, checks: list[dict], registered: int = 0,
              registration_satisfies: bool = False) -> dict:
    required = [item for item in checks if item["required"]]
    ready = (registration_satisfies and bool(registered)) or (bool(required) and all(item["configured"] for item in required))
    return {
        "id": provider_id,
        "name": name,
        "status": "ready" if ready else "attention",
        "configured_connections": registered,
        "checks": checks,
        "missing": [item["label"] for item in required if not item["configured"]] if not ready else [],
    }


def get_readiness(organization_id: str) -> dict:
    connections = integration_store.list_connections(organization_id)
    counts: dict[str, int] = {}
    for connection in connections:
        provider = str(connection.get("provider", ""))
        if connection.get("status") in {"configured", "connected", "active"}:
            counts[provider] = counts.get(provider, 0) + 1

    aws_identity = counts.get("aws", 0) > 0 or ((_present("AWS_ACCESS_KEY_ID") and _present("AWS_SECRET_ACCESS_KEY")) or _present("AWS_WEB_IDENTITY_TOKEN_FILE"))
    providers = [
        _provider("aws", "Amazon Web Services", [
            _check("identity", "Encrypted AWS credential", aws_identity, "Select Connect AWS and enter a restricted access key."),
            _check("region", "AWS region", aws_identity or _present("AWS_REGION") or _present("AWS_DEFAULT_REGION"), "Enter the account's primary AWS region."),
            _check("role", "Customer role ARN", _present("AWS_ROLE_ARN"), "Add a role ARN only when cross-account role access is required.", required=False),
        ], counts.get("aws", 0), registration_satisfies=True),
        _provider("slack", "Slack", [
            _check("bot_token", "Slack bot token", _present("SLACK_BOT_TOKEN"), "Set SLACK_BOT_TOKEN in Render."),
            _check("app_token", "Slack app token", _present("SLACK_APP_TOKEN"), "Set SLACK_APP_TOKEN in Render."),
            _check("channel", "Slack channel", _present("SLACK_CHANNEL"), "Set SLACK_CHANNEL in Render."),
        ], counts.get("slack", 0)),
        _provider("vmware", "VMware vCenter", [
            _check("gateway", "Tenant gateway registration", counts.get("vmware", 0) > 0, "Create and enroll a customer gateway for private vCenter access."),
        ], counts.get("vmware", 0), registration_satisfies=True),
        _provider("sccm", "Microsoft SCCM", [
            _check("gateway", "Tenant gateway registration", counts.get("sccm", 0) > 0, "Create and enroll a Windows customer gateway for SCCM."),
        ], counts.get("sccm", 0), registration_satisfies=True),
        _provider("email", "Inbound email", [
            _check("imap_host", "IMAP server", _present("IMAP_HOST"), "Set IMAP_HOST in Render."),
            _check("imap_identity", "IMAP service identity", _present("IMAP_USERNAME") and _present("IMAP_PASSWORD"), "Set the IMAP service account credentials in Render."),
        ], counts.get("gmail", 0)),
    ]
    ready = sum(item["status"] == "ready" for item in providers)
    return {
        "summary": {"ready": ready, "attention": len(providers) - ready, "total": len(providers)},
        "providers": providers,
        "security": "Secret values and vault references are never returned by this endpoint.",
    }

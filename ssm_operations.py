"""Approval-gated AWS Systems Manager runbook execution.

Only allowlisted operation slugs can resolve to the fixed OpsAgent document
namespace. Browser/LLM supplied shell or PowerShell is never accepted.
"""
import re
import time
import json
from datetime import datetime, timezone
from uuid import uuid4

import config
import ops_log
from aws_operations import _session


_SLUG = re.compile(r"^[a-z][a-z0-9_]{2,79}$")
_INSTANCE = re.compile(r"^i-[0-9a-f]{8,17}$", re.I)
_PARAMETER = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
_DOMAIN = re.compile(r"^(?=.{3,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$")
_SECRET_ARN = re.compile(r"^arn:(?:aws|aws-us-gov|aws-cn):secretsmanager:[a-z0-9-]+:\d{12}:secret:[A-Za-z0-9/_+=.@-]+$")
_SECRET_NAME = re.compile(r"^[A-Za-z0-9/_+=.@-]{1,512}$")


def normalize_action(value):
    action = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")
    if not _SLUG.fullmatch(action):
        raise ValueError("Invalid operation name")
    return action


def document_name(action):
    return f"{config.SSM_DOCUMENT_PREFIX}{normalize_action(action)}"


def _parameters(values):
    result = {}
    for key, value in (values or {}).items():
        if not _PARAMETER.fullmatch(str(key)):
            raise ValueError(f"Invalid parameter name: {key}")
        if isinstance(value, (dict, list)):
            raise ValueError(f"Parameter {key} must be a string, number, or boolean")
        text = str(value if value is not None else "")
        if len(text) > 4096:
            raise ValueError(f"Parameter {key} is too long")
        result[str(key)] = [text]
    return result


def _validate_action_parameters(action, values):
    """Apply semantic checks that cannot safely be delegated to an SSM document."""
    values = values or {}
    if action != "join_computer_to_domain":
        return
    domain = str(values.get("DomainName") or "").strip()
    secret_id = str(values.get("DomainCredentialSecretId") or "").strip()
    if not _DOMAIN.fullmatch(domain):
        raise ValueError("Enter a valid Active Directory DNS domain, for example corp.example.com")
    if secret_id.startswith("arn:aws:iam:"):
        raise ValueError("Domain credential secret must be an AWS Secrets Manager secret, not an IAM role ARN")
    if not (_SECRET_ARN.fullmatch(secret_id) or _SECRET_NAME.fullmatch(secret_id)):
        raise ValueError("Enter a valid AWS Secrets Manager secret name or ARN")
    secret_name = secret_id.split(":secret:", 1)[-1] if ":secret:" in secret_id else secret_id
    if not secret_name.startswith("opsagent/domain-join/"):
        raise ValueError("Domain join credentials must use a secret under opsagent/domain-join/")


def execute(action, instance_id, *, parameters=None, region=None, approved=False, actor="unknown"):
    action = normalize_action(action)
    instance_id = str(instance_id or "").strip()
    request_id = f"SSM-{uuid4().hex[:10].upper()}"
    if not approved:
        raise PermissionError("Explicit approval is required")
    if action not in config.SSM_ALLOWED_ACTIONS:
        raise PermissionError(f"Operation '{action}' is not in SSM_ALLOWED_ACTIONS")
    if not _INSTANCE.fullmatch(instance_id):
        raise ValueError("An exact EC2 instance ID is required")
    _validate_action_parameters(action, parameters)
    client = _session().client("ssm", region_name=region or config.AWS_REGION)
    info = client.describe_instance_information(
        Filters=[{"Key": "InstanceIds", "Values": [instance_id]}], MaxResults=5
    ).get("InstanceInformationList", [])
    if not info or info[0].get("PingStatus") != "Online":
        raise RuntimeError("Target is not an online SSM-managed instance")
    document = document_name(action)
    ops_log.write("ssm", "INFO", "operation_started", json.dumps({"requester": actor, "action": action, "target": instance_id, "document": document, "status": "requested"}), request_id)
    if config.SSM_OPERATIONS_DRY_RUN:
        result = {"success": True, "dry_run": True, "verified": True, "request_id": request_id, "requester": actor, "action": action, "instance_id": instance_id, "document": document, "status": "DryRunValidated", "platform": info[0].get("PlatformType")}
        ops_log.write("ssm", "INFO", "operation_dry_run_validated", json.dumps(result), request_id)
        return result
    try:
        response = client.send_command(
            InstanceIds=[instance_id], DocumentName=document,
            Parameters=_parameters(parameters), TimeoutSeconds=config.SSM_COMMAND_TIMEOUT_SECONDS,
            Comment=f"OpsAgent approved request {request_id} by {actor}"[:100],
        )
    except client.exceptions.InvalidDocument as error:
        raise RuntimeError(
            f"Required SSM document '{document}' is not deployed in region "
            f"'{region or config.AWS_REGION}'. Publish the matching document before executing this operation."
        ) from error
    command_id = response["Command"]["CommandId"]
    deadline = time.monotonic() + config.SSM_COMMAND_TIMEOUT_SECONDS
    invocation = None
    while time.monotonic() < deadline:
        try:
            invocation = client.get_command_invocation(CommandId=command_id, InstanceId=instance_id)
        except client.exceptions.InvocationDoesNotExist:
            time.sleep(2)
            continue
        if invocation.get("Status") in {"Success", "Cancelled", "TimedOut", "Failed", "Cancelling"}:
            break
        time.sleep(2)
    status = (invocation or {}).get("Status", "TimedOut")
    result = {
        "success": status == "Success", "verified": status == "Success", "dry_run": False,
        "request_id": request_id, "command_id": command_id, "requester": actor, "action": action,
        "instance_id": instance_id, "document": document, "status": status,
        "stdout": str((invocation or {}).get("StandardOutputContent") or "")[-12000:],
        "stderr": str((invocation or {}).get("StandardErrorContent") or "")[-12000:],
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    ops_log.write("ssm", "INFO" if result["success"] else "ERROR", "operation_completed" if result["success"] else "operation_failed", json.dumps(result), request_id)
    return result


def audit_recent(limit=500):
    rows = ops_log.recent(component="ssm", limit=limit)
    events = []
    for row in rows:
        try:
            details = json.loads(row.get("Details") or "{}")
        except (TypeError, json.JSONDecodeError):
            details = {}
        events.append({
            "time": row.get("Time"), "request_id": row.get("Correlation ID"),
            "requester": details.get("requester", "unknown"),
            "operation": details.get("action", row.get("Event")),
            "target": details.get("target", details.get("instance_id", "—")),
            "document": details.get("document", "—"),
            "status": details.get("status", row.get("Event")),
            "result": "success" if details.get("success") else ("failed" if details.get("success") is False else "pending"),
        })
    return events

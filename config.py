"""
config.py
---------
Centralized configuration for the Server Downtime Automation Agent.

All credentials and tunable settings are loaded from environment variables
(via a local .env file). Nothing in this file should contain real secrets -
copy .env.example to .env and fill in your own values.
"""

import os
from dotenv import load_dotenv

# Load variables from a local .env file into the process environment.
# If .env does not exist, this is a no-op and os.getenv() falls back to defaults.
load_dotenv()

# --- Slack (Socket Mode) ----------------------------------------------------
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")          # xoxb-... bot user token
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")          # xapp-... app-level token (Socket Mode)
SLACK_CHANNEL = os.getenv("SLACK_CHANNEL", "#ops-alerts")  # channel the bot watches & reports to
GRAFANA_SLACK_BOT_NAME = os.getenv("GRAFANA_SLACK_BOT_NAME", "Grafana Alerts").strip()
SLACK_APPROVERS = {
    value.strip()
    for value in os.getenv("SLACK_APPROVERS", "").split(",")
    if value.strip()
}
SLACK_APPROVAL_EXPIRY_MINUTES = int(os.getenv("SLACK_APPROVAL_EXPIRY_MINUTES", "15"))
SLACK_AWS_VERIFY_SECONDS = int(os.getenv("SLACK_AWS_VERIFY_SECONDS", "120"))
SLACK_ALLOW_SELF_APPROVAL = os.getenv(
    "SLACK_ALLOW_SELF_APPROVAL", "false"
).strip().lower() in {"1", "true", "yes", "on"}

# --- OpenAI ------------------------------------------------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_INPUT_COST_PER_MILLION = float(os.getenv("OPENAI_INPUT_COST_PER_MILLION", "0.15"))
OPENAI_OUTPUT_COST_PER_MILLION = float(os.getenv("OPENAI_OUTPUT_COST_PER_MILLION", "0.60"))

# --- PostgreSQL server inventory --------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
INVENTORY_EDIT_ENABLED = os.getenv("INVENTORY_EDIT_ENABLED", "false").strip().lower() in {
    "1", "true", "yes", "on"
}
APP_SIGNUP_ENABLED = os.getenv("APP_SIGNUP_ENABLED", "false").strip().lower() in {
    "1", "true", "yes", "on"
}

# --- Default remote investigation target ------------------------------------
# DEFAULT_TARGET_HOST is provider-neutral. EC2_HOST remains a compatibility
# fallback for existing installations and can be removed after migration.
DEFAULT_TARGET_HOST = os.getenv("DEFAULT_TARGET_HOST", os.getenv("EC2_HOST", "")).strip()
EC2_HOST = DEFAULT_TARGET_HOST
EC2_USERNAME = os.getenv("EC2_USERNAME", "ubuntu")
EC2_KEY_PATH = os.getenv("EC2_KEY_PATH", "./opsagent-key.pem")
EC2_SSH_PORT = int(os.getenv("EC2_SSH_PORT", "22"))

# --- AWS control-plane automation -------------------------------------------
# Mutations are denied unless the individual action is explicitly allowlisted.
AWS_REGION = os.getenv("AWS_REGION", "ap-south-1").strip()
AWS_PROFILE = os.getenv("AWS_PROFILE", "").strip()
AWS_ROLE_ARN = os.getenv("AWS_ROLE_ARN", "").strip()
AWS_EXTERNAL_ID = os.getenv("AWS_EXTERNAL_ID", "").strip()
AWS_ROLE_SESSION_NAME = os.getenv("AWS_ROLE_SESSION_NAME", "opsagent-connector").strip()
if AWS_PROFILE.lower() in {"()", "none", "null"}:
    AWS_PROFILE = ""
AWS_INVENTORY_SYNC_ENABLED = os.getenv(
    "AWS_INVENTORY_SYNC_ENABLED", "true"
).strip().lower() in {"1", "true", "yes", "on"}
AWS_INVENTORY_SYNC_INTERVAL_SECONDS = max(
    30, int(os.getenv("AWS_INVENTORY_SYNC_INTERVAL_SECONDS", "60"))
)
AWS_INVENTORY_REGIONS = tuple(
    value.strip() for value in os.getenv("AWS_INVENTORY_REGIONS", AWS_REGION).split(",")
    if value.strip()
)
AWS_DRY_RUN = os.getenv("AWS_DRY_RUN", "true").strip().lower() in {"1", "true", "yes", "on"}
AWS_ALLOWED_ACTIONS = {
    value.strip().lower()
    for value in os.getenv("AWS_ALLOWED_ACTIONS", "").split(",")
    if value.strip()
}
SSM_OPERATIONS_DRY_RUN = os.getenv("SSM_OPERATIONS_DRY_RUN", "true").strip().lower() in {"1", "true", "yes", "on"}
SSM_ALLOWED_ACTIONS = {
    value.strip().lower()
    for value in os.getenv("SSM_ALLOWED_ACTIONS", "").split(",")
    if value.strip()
}
SSM_DOCUMENT_PREFIX = os.getenv("SSM_DOCUMENT_PREFIX", "OpsAgent-").strip() or "OpsAgent-"
SSM_COMMAND_TIMEOUT_SECONDS = max(30, int(os.getenv("SSM_COMMAND_TIMEOUT_SECONDS", "600")))
AWS_DELETE_VOLUME_REQUIRED_TAG_KEY = os.getenv(
    "AWS_DELETE_VOLUME_REQUIRED_TAG_KEY", "OpsAgentDeletable"
).strip()
AWS_DELETE_VOLUME_REQUIRED_TAG_VALUE = os.getenv(
    "AWS_DELETE_VOLUME_REQUIRED_TAG_VALUE", "true"
).strip()

# --- VMware ESXi / vCenter control-plane automation --------------------------
VMWARE_ENDPOINT = os.getenv("VMWARE_ENDPOINT", "").strip()
VMWARE_PORT = int(os.getenv("VMWARE_PORT", "443"))
VMWARE_USERNAME = os.getenv("VMWARE_USERNAME", "").strip()
VMWARE_PASSWORD = os.getenv("VMWARE_PASSWORD", "")
VMWARE_VERIFY_SSL = os.getenv("VMWARE_VERIFY_SSL", "true").strip().lower() in {
    "1", "true", "yes", "on"
}
VMWARE_DRY_RUN = os.getenv("VMWARE_DRY_RUN", "true").strip().lower() in {
    "1", "true", "yes", "on"
}
VMWARE_ALLOWED_ACTIONS = {
    value.strip().lower()
    for value in os.getenv("VMWARE_ALLOWED_ACTIONS", "").split(",")
    if value.strip()
}

# --- SCCM/MECM patch orchestration -------------------------------------------
# Simulation is free and makes no calls to a Configuration Manager environment.
SCCM_MODE = os.getenv("SCCM_MODE", "simulation").strip().lower()
SCCM_ALLOWED_ACTIONS = {
    value.strip().lower()
    for value in os.getenv("SCCM_ALLOWED_ACTIONS", "create_patch_deployment").split(",")
    if value.strip()
}
SCCM_ALLOW_REBOOT = os.getenv("SCCM_ALLOW_REBOOT", "false").strip().lower() in {
    "1", "true", "yes", "on"
}
SCCM_INSTANCE_ID = os.getenv("SCCM_INSTANCE_ID", "").strip()
SCCM_REGION = os.getenv("SCCM_REGION", AWS_REGION).strip() or AWS_REGION
SCCM_INVENTORY_DOCUMENT = os.getenv(
    "SCCM_INVENTORY_DOCUMENT", "OpsAgent-sccm_inventory"
).strip()
SCCM_COMMAND_TIMEOUT_SECONDS = max(
    30, int(os.getenv("SCCM_COMMAND_TIMEOUT_SECONDS", "300"))
)
SCCM_CACHE_SECONDS = max(5, int(os.getenv("SCCM_CACHE_SECONDS", "60")))
SCCM_SIMULATED_COLLECTIONS = tuple(
    value.strip()
    for value in os.getenv(
        "SCCM_SIMULATED_COLLECTIONS",
        "OPSAGENT-TEST-D1,OPSAGENT-TEST-D2,OPSAGENT-INFRA-D1,OPSAGENT-INFRA-D2,OPSAGENT-PROD-D1,OPSAGENT-PROD-D2,OPSAGENT-PROD-D3,OPSAGENT-PROD-D4",
    ).split(",")
    if value.strip()
)

# --- Optional Windows EC2 target ---------------------------------------------
WINDOWS_EC2_HOST = os.getenv("WINDOWS_EC2_HOST", "").strip()
WINDOWS_EC2_USERNAME = os.getenv("WINDOWS_EC2_USERNAME", "Administrator").strip()
WINDOWS_EC2_KEY_PATH = os.getenv("WINDOWS_EC2_KEY_PATH", EC2_KEY_PATH).strip()
WINDOWS_EC2_SSH_PORT = int(os.getenv("WINDOWS_EC2_SSH_PORT", "22"))
TARGET_GATEWAY_IP = os.getenv("TARGET_GATEWAY_IP", "").strip()

# Slack messages without an IP use the Windows VM by default when configured.
# Set SLACK_TARGET_HOST explicitly to choose a different Slack-only target.
SLACK_TARGET_HOST = os.getenv(
    "SLACK_TARGET_HOST", WINDOWS_EC2_HOST or EC2_HOST or ""
).strip()


def connection_profile(host, os_preference=None, inventory_record=None):
    """Return host-specific SSH credentials and OS preference."""
    inventory_record = inventory_record or {}
    inventory_connection = inventory_record.get("connection") or {}
    inventory_os = str(inventory_record.get("os_type") or "").strip().lower()
    if inventory_record:
        return {
            "username": inventory_connection.get("username") or (
                WINDOWS_EC2_USERNAME if inventory_os == "windows" else EC2_USERNAME
            ),
            "key_path": inventory_connection.get("key_path") or (
                WINDOWS_EC2_KEY_PATH if inventory_os == "windows" else EC2_KEY_PATH
            ),
            "port": int(inventory_connection.get("port") or 22),
            "os_type": inventory_os if inventory_os in {"linux", "windows"} else SERVER_OS,
        }
    force_windows = (os_preference or "").strip().lower() == "windows"
    if force_windows or (WINDOWS_EC2_HOST and (host or "").strip().lower() == WINDOWS_EC2_HOST.lower()):
        return {
            "username": WINDOWS_EC2_USERNAME,
            "key_path": WINDOWS_EC2_KEY_PATH,
            "port": WINDOWS_EC2_SSH_PORT,
            "os_type": "windows",
        }
    return {
        "username": EC2_USERNAME,
        "key_path": EC2_KEY_PATH,
        "port": EC2_SSH_PORT,
        "os_type": SERVER_OS,
    }

# --- Incident response --------------------------------------------------------
MONITORING_SERVICE_NAME = os.getenv("MONITORING_SERVICE_NAME", "Alloy")
CRITICAL_SERVICE_NAMES = [
    name.strip().lower()
    for name in os.getenv("CRITICAL_SERVICE_NAMES", "").split(",")
    if name.strip()
]
MONITORING_SERVICE_INSTALL_HINT = os.getenv(
    "MONITORING_SERVICE_INSTALL_HINT",
    "Install and enable the expected monitoring service on this host, or update MONITORING_SERVICE_NAME if this server uses a different agent.",
)
ONCALL_SLACK_USER = os.getenv("ONCALL_SLACK_USER", "dhanashekar805")
SERVER_OS = os.getenv("SERVER_OS", "auto").strip().lower()

# --- Optional email escalation -----------------------------------------------
# When these values are configured, genuine incidents are also emailed to the
# application owner. Email remains disabled when APPLICATION_OWNER_EMAIL is blank.
APPLICATION_OWNER_EMAIL = os.getenv("APPLICATION_OWNER_EMAIL", "").strip()
SERVER_TEAM_EMAIL = os.getenv("SERVER_TEAM_EMAIL", "").strip()
SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", SMTP_USERNAME).strip()
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").strip().lower() in {"1", "true", "yes", "on"}
# --- Optional inbound email approval workflow -------------------------------
INBOUND_EMAIL_ENABLED = os.getenv("INBOUND_EMAIL_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
IMAP_HOST = os.getenv("IMAP_HOST", "").strip()
IMAP_PORT = int(os.getenv("IMAP_PORT", "993"))
IMAP_USERNAME = os.getenv("IMAP_USERNAME", SMTP_USERNAME).strip()
IMAP_PASSWORD = os.getenv("IMAP_PASSWORD", SMTP_PASSWORD)
IMAP_FOLDER = os.getenv("IMAP_FOLDER", "INBOX").strip()
INBOUND_EMAIL_POLL_SECONDS = int(os.getenv("INBOUND_EMAIL_POLL_SECONDS", "30"))
INBOUND_EMAIL_LOOKBACK_MINUTES = int(os.getenv("INBOUND_EMAIL_LOOKBACK_MINUTES", "60"))
EMAIL_REQUEST_SENDERS = {v.strip().lower() for v in os.getenv("EMAIL_REQUEST_SENDERS", "").split(",") if v.strip()}
EMAIL_APPROVERS = {v.strip().lower() for v in os.getenv("EMAIL_APPROVERS", "").split(",") if v.strip()}
EMAIL_APPROVAL_EXPIRY_MINUTES = int(os.getenv("EMAIL_APPROVAL_EXPIRY_MINUTES", "30"))
EMAIL_AWS_VERIFY_SECONDS = int(os.getenv("EMAIL_AWS_VERIFY_SECONDS", "120"))
EMAIL_APPROVAL_RETENTION_RECORDS = int(os.getenv("EMAIL_APPROVAL_RETENTION_RECORDS", "1000"))
APPLICATION_OWNER_UTILIZATION_THRESHOLD = float(
    os.getenv("APPLICATION_OWNER_UTILIZATION_THRESHOLD", "75")
)
DEFAULT_ORGANIZATION_ID = os.getenv("OPSAGENT_DEFAULT_ORGANIZATION_ID", "").strip()
UTILIZATION_RECHECK_SECONDS = int(os.getenv("UTILIZATION_RECHECK_SECONDS", "300"))

# --- Agent behaviour tuning ----------------------------------------------------
# Any message containing one of these keywords (case-insensitive) in the
# watched Slack channel will trigger an investigation.
ALERT_KEYWORDS = [
    kw.strip().lower()
    for kw in os.getenv(
        "ALERT_KEYWORDS",
        "down,alert,server,issue,error,fail,outage,unreachable,crash,not responding",
    ).split(",")
    if kw.strip()
]

# Safety cap on how many reasoning/tool-call round-trips the agent can make
# for a single incident, to prevent runaway loops burning API credits.
MAX_AGENT_ITERATIONS = int(os.getenv("MAX_AGENT_ITERATIONS", "6"))

# Timeouts (seconds)
SSH_TIMEOUT = int(os.getenv("SSH_TIMEOUT", "10"))
SSH_COMMAND_TIMEOUT = int(os.getenv("SSH_COMMAND_TIMEOUT", "30"))
RETRY_ATTEMPTS = int(os.getenv("RETRY_ATTEMPTS", "3"))
RETRY_DELAY_SECONDS = float(os.getenv("RETRY_DELAY_SECONDS", "1"))
STARTUP_ALERT_LOOKBACK_MINUTES = int(os.getenv("STARTUP_ALERT_LOOKBACK_MINUTES", "60"))
SLACK_ALERT_POLL_SECONDS = int(os.getenv("SLACK_ALERT_POLL_SECONDS", "30"))
HUMAN_MENTION_LOOKBACK_MINUTES = int(os.getenv("HUMAN_MENTION_LOOKBACK_MINUTES", "10"))
ALERT_DEDUP_MINUTES = int(os.getenv("ALERT_DEDUP_MINUTES", "10"))
DISK_ALERT_MUTE_MINUTES = int(os.getenv("DISK_ALERT_MUTE_MINUTES", "20"))

# Variables that MUST be present for the agent to function at all.
_REQUIRED_VARS = {
    "SLACK_BOT_TOKEN": SLACK_BOT_TOKEN,
    "SLACK_APP_TOKEN": SLACK_APP_TOKEN,
    "OPENAI_API_KEY": OPENAI_API_KEY,
    "DEFAULT_TARGET_HOST (or legacy EC2_HOST)": DEFAULT_TARGET_HOST,
    "DATABASE_URL": DATABASE_URL,
}


def validate():
    """
    Fail fast and loud if required configuration is missing, instead of
    letting the bot start and crash confusingly on the first alert.
    Call this once at startup (see main.py).
    """
    missing = [name for name, value in _REQUIRED_VARS.items() if not value]
    if missing:
        raise EnvironmentError(
            "Missing required environment variable(s): "
            + ", ".join(missing)
            + ". Copy .env.example to .env and fill in the values."
        )

    if not os.path.isfile(EC2_KEY_PATH):
        raise EnvironmentError(
            f"EC2_KEY_PATH does not point to an existing file: '{EC2_KEY_PATH}'. "
            "Check the path to your .pem private key."
        )

    if SERVER_OS not in {"auto", "linux", "windows"}:
        raise EnvironmentError("SERVER_OS must be one of: auto, linux, windows.")

"""FastAPI control plane over the existing operational Python services."""
import os
import threading
from pathlib import Path
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel, Field, SecretStr

import ai_usage
import agent
import alert_metrics
import auth
import chat_store
import chat_operations
import connector_readiness
import connector_testing
import credential_store
import config
import database
import email_metrics
import demo_requests
import decommission_inventory
import health_status
import hardware_monitoring
import grafana_connector
import iam
import integration_store
import monitoring_connectors
import ops_log
import server_inventory
import sccm_operations
import sccm_patch_pipeline
import settings_store
import ssm_operations
import vmware_operations
from backend import authorization, security
from backend.oauth import PROVIDERS, oauth, public_registry
from providers import aws
import psycopg

app = FastAPI(title="OpsAgent One API", description="One intelligent platform for every infrastructure operation.", version="0.1.0", docs_url="/api/docs", openapi_url="/api/openapi.json")
app.add_middleware(SessionMiddleware, secret_key=security.application_secret(), https_only=os.getenv("OPSAGENT_COOKIE_SECURE", "false").lower() == "true", same_site="lax")
origins = [value.strip() for value in os.getenv("OPSAGENT_CORS_ORIGINS", "http://localhost:5173").split(",") if value.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(psycopg.OperationalError)
async def database_unavailable(_request: Request, _error: psycopg.OperationalError):
    """Return a stable response while PostgreSQL starts or temporarily recovers."""
    return JSONResponse(
        status_code=503,
        content={"detail": "Database is temporarily unavailable. Retry shortly."},
        headers={"Retry-After": "5"},
    )


@app.on_event("startup")
def start_background_connectors():
    """Run inventory and messaging connectors with the API process."""
    if os.getenv("OPSAGENT_CONNECTORS_IN_API", "true").lower() not in {"1", "true", "yes", "on"}:
        return
    aws.start_inventory_sync()

    # Gmail has its own daemon poller and safely no-ops when disabled.
    try:
        import inbound_email
        inbound_email.start()
    except Exception as exc:
        health_status.update("inbound_email", "error", f"Startup failed: {exc}")
        ops_log.write("inbound_email", "ERROR", "connector_start_failed", str(exc))

    # Slack Socket Mode blocks, so keep it beside FastAPI in a daemon thread.
    try:
        import config
        if not (config.SLACK_BOT_TOKEN and config.SLACK_APP_TOKEN):
            health_status.update("slack", "disabled", "Slack credentials are not configured")
            return
        import main as operations_runtime
        import slack_actions
        import slack_handler
        slack_handler.register_alert_listener(
            operations_runtime.on_alert,
            on_mention=operations_runtime.on_mention,
            on_action=operations_runtime.on_slack_action,
            action_recovery=slack_actions.recover_pending_thread_approvals,
        )

        def run_slack():
            try:
                slack_handler.start()
            except Exception as exc:
                health_status.update("slack", "error", f"Worker stopped: {exc}")
                ops_log.write("slack", "ERROR", "connector_stopped", str(exc))

        threading.Thread(target=run_slack, name="opsagent-slack", daemon=True).start()
    except Exception as exc:
        health_status.update("slack", "error", f"Startup failed: {exc}")
        ops_log.write("slack", "ERROR", "connector_start_failed", str(exc))


class LoginRequest(BaseModel):
    username: str
    password: str


class SignupRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=12, max_length=256)
    country: str = Field(min_length=2, max_length=80)
    mobile_number: str = Field(min_length=7, max_length=24, pattern=r"^\+?[0-9 ()-]{7,24}$")


class MfaCodeRequest(BaseModel):
    code: str = Field(min_length=6, max_length=8)


class TerminationApprovalRequest(BaseModel):
    session_id: str
    mfa_code: str = Field(min_length=6, max_length=8)
    backup_confirmed: bool = False


class AwsConfigurationRequest(BaseModel):
    region: str = Field(pattern=r"^[a-z]{2}(?:-gov)?-[a-z]+-\d$")


class DemoRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    business_email: str = Field(min_length=5, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    company: str = Field(min_length=2, max_length=160)
    job_role: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=40)
    estate_size: str | None = Field(default=None, max_length=80)
    interests: list[str] = Field(default_factory=list, max_length=12)
    message: str | None = Field(default=None, max_length=2000)
    website: str | None = Field(default=None, max_length=200)


class ChatRequest(BaseModel):
    session_id: str
    message: str
    persona: str = "Senior Infrastructure Architect"
    attachments: list[dict] = Field(default_factory=list)


class AwsOperationRequest(BaseModel):
    action: str
    identifier: str
    confirmation: str
    region: str | None = None
    instance_type: str | None = None
    volume_id: str | None = None
    size_gib: int | None = None
    network_interface_id: str | None = None
    snapshot_id: str | None = None


class AwsProvisionRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    region: str = Field(default="us-east-1", max_length=30)
    os: str = Field(max_length=80)
    instance_type: str = Field(default="t3.medium", max_length=30)
    vpc: str = Field(default="Default VPC", max_length=128)
    subnet: str = Field(default="Auto-select private subnet", max_length=128)
    security_group: str = Field(max_length=128)
    storage_gib: int = Field(default=80, ge=30, le=2048)
    environment: str = Field(default="Development", max_length=40)
    instance_profile: str = Field(default="OpsAgentManagedInstanceProfile", max_length=128)
    key_name: str | None = Field(default=None, max_length=255)
    confirmation: str = Field(default="", max_length=200)


class SsmOperationRequest(BaseModel):
    action: str
    instance_id: str
    confirmation: str
    region: str | None = None
    parameters: dict[str, str | int | float | bool] = Field(default_factory=dict)


class SccmPatchCycleRequest(BaseModel):
    name: str
    release_date: str
    test_date: str
    production_date: str
    deadline_date: str
    kb_ids: list[str] = Field(default_factory=list)
    software_update_group: str
    deployment_package: str
    test_collection: str
    pilot_collection: str | None = None
    production_collection: str
    change_system: str = "ServiceNow"
    change_id: str | None = None
    stakeholder_emails: list[str] = Field(default_factory=list)
    application_emails: list[str] = Field(default_factory=list)


class SccmStageRequest(BaseModel):
    evidence: dict = Field(default_factory=dict)


class HardwareTicketRequest(BaseModel):
    alert_index: int = Field(ge=0)


class UserUpdateRequest(BaseModel):
    role: str
    enabled: bool


class VMwareOperationRequest(BaseModel):
    action: str
    target: str
    confirmation: str
    parameters: dict = Field(default_factory=dict)


class PasswordRequest(BaseModel):
    current_password: str
    new_password: str


class SettingsRequest(BaseModel):
    ui_version: str = "enterprise_light_v1"
    theme: str = "light"
    font_size: str = "compact"
    density: str = "compact"
    timezone: str = "Asia/Kolkata"
    date_format: str = "DD MMM YYYY"
    model_provider: str = "openai"
    model_name: str = "gpt-4o-mini"
    email_notifications: bool = True
    operation_notifications: bool = True
    extensions: dict[str, bool] = Field(default_factory=dict)


class OrganizationRequest(BaseModel):
    name: str


class IntegrationConnectionRequest(BaseModel):
    provider: str
    display_name: str = Field(min_length=2, max_length=120)
    connection_type: str
    endpoint: str | None = Field(default=None, max_length=500)
    credential_reference: str | None = Field(default=None, max_length=500)
    configuration: dict = Field(default_factory=dict)


class SecureIntegrationConnectionRequest(BaseModel):
    provider: str
    display_name: str = Field(min_length=2, max_length=120)
    endpoint: str | None = Field(default=None, max_length=500)
    configuration: dict = Field(default_factory=dict)
    credentials: dict[str, SecretStr]


class GatewayRegistrationRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    platform: str = Field(default="windows", pattern="^(windows|linux|kubernetes)$")


class MembershipRequest(BaseModel):
    role: str
    status: str = "active"


class InvitationRequest(BaseModel):
    email: str
    role: str = "Viewer"


def current_user(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Authentication required")
    claims = security.verify(authorization.split(" ", 1)[1])
    if not claims:
        raise HTTPException(401, "Session expired or invalid")
    persisted = auth.get_user(claims["sub"])
    if not persisted or not persisted.get("enabled"):
        raise HTTPException(401, "Account is unavailable")
    try:
        return iam.context(persisted, claims.get("org"))
    except PermissionError as error:
        raise HTTPException(403, str(error)) from error


def require_permission(permission: str):
    """FastAPI dependency enforcing one central organization-role policy."""
    def dependency(user=Depends(current_user)):
        try:
            authorization.require_organization(user)
        except PermissionError as error:
            raise HTTPException(403, str(error)) from error
        if not authorization.allowed(user, permission):
            raise HTTPException(403, f"The {authorization.role_for(user) or 'current'} role lacks the {permission} permission")
        return user
    return dependency


@app.get("/api/v1/health")
def health():
    return {"service": "OpsAgent One API", "status": "healthy", "version": app.version}


@app.get("/api/v1/ready")
def ready():
    """Readiness probe used by deployment platforms and load balancers."""
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    return {"service": "OpsAgent One API", "status": "ready", "database": "connected", "version": app.version}


@app.post("/api/v1/public/demo-requests", status_code=201)
def request_demo(request: DemoRequest):
    # Hidden honeypot field: silently accept automated submissions without storing them.
    if request.website:
        return {"request_id": "accepted", "status": "received"}
    try:
        result = demo_requests.create(request.model_dump(exclude={"website"}))
    except Exception as error:
        raise HTTPException(503, "Demo request service is temporarily unavailable") from error
    return {**result, "message": "Thank you. Our team will contact you to schedule the demonstration."}


@app.post("/api/v1/auth/login")
def login(request: LoginRequest):
    user, error = auth.authenticate(request.username, request.password)
    if not user:
        raise HTTPException(401, error or "Invalid credentials")
    user = iam.context(user)
    return {"access_token": security.issue(user), "token_type": "bearer", "user": user}


@app.post("/api/v1/auth/signup", status_code=201)
def signup(request: SignupRequest):
    if auth.get_user(request.username):
        raise HTTPException(409, "An account with this username already exists")
    try:
        user = auth.signup_user(request.username, request.password, display_name=request.username)
        organization = iam.create_organization(user["username"], f"{user['display_name']}'s Workspace")
        user = iam.context(user, organization["organization_id"])
    except PermissionError as error:
        raise HTTPException(403, str(error)) from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    return {"access_token": security.issue(user), "token_type": "bearer", "user": user}


@app.get("/api/v1/auth/me")
def me(user=Depends(current_user)):
    return user


@app.get("/api/v1/auth/mfa/status")
def get_mfa_status(_user=Depends(current_user)):
    return auth.mfa_status(_user["username"])


@app.post("/api/v1/auth/mfa/setup")
def setup_mfa(_user=Depends(current_user)):
    return auth.begin_mfa_setup(_user["username"])


@app.post("/api/v1/auth/mfa/enable")
def enable_mfa(request: MfaCodeRequest, _user=Depends(current_user)):
    if not auth.verify_mfa(_user["username"], request.code, enable=True):
        raise HTTPException(422, "Invalid authenticator code")
    return {"enabled": True}


@app.get("/api/v1/auth/providers")
def authentication_providers():
    return public_registry()


@app.get("/api/v1/auth/oauth/{provider}/start")
async def oauth_start(provider: str, request: Request):
    if provider not in PROVIDERS:
        raise HTTPException(404, "Unknown identity provider")
    client = oauth.create_client(provider)
    if not client:
        raise HTTPException(503, f"{PROVIDERS[provider]['label']} sign-in is not configured")
    public_base = os.getenv("OPSAGENT_OAUTH_CALLBACK_BASE", os.getenv("OPSAGENT_FRONTEND_URL", "http://localhost:5173")).rstrip("/")
    redirect_uri = f"{public_base}/api/v1/auth/oauth/{provider}/callback"
    return await client.authorize_redirect(request, redirect_uri)


@app.get("/api/v1/auth/oauth/{provider}/callback", name="oauth_callback")
async def oauth_callback(provider: str, request: Request):
    client = oauth.create_client(provider)
    if not client:
        raise HTTPException(503, "Identity provider is not configured")
    token = await client.authorize_access_token(request)
    if provider == "github":
        profile = (await client.get("user", token=token)).json()
        if not profile.get("email"):
            emails = (await client.get("user/emails", token=token)).json()
            profile["email"] = next((item["email"] for item in emails if item.get("primary") and item.get("verified")), None)
        subject, email, name = str(profile["id"]), profile.get("email"), profile.get("name") or profile.get("login")
    else:
        profile = token.get("userinfo") or await client.userinfo(token=token)
        subject, email, name = profile.get("sub"), profile.get("email") or profile.get("preferred_username"), profile.get("name")
    if not subject or not email:
        raise HTTPException(400, "The identity provider did not return a verified email address")
    external_user = auth.authenticate_external(provider, subject, email, name)
    iam.accept_pending_invitations(external_user, email)
    organization = iam.ensure_external_owner(external_user)
    user = iam.context(external_user, organization["organization_id"])
    frontend = os.getenv("OPSAGENT_FRONTEND_URL", "http://localhost:5173").rstrip("/")
    return RedirectResponse(f"{frontend}/#access_token={security.issue(user)}")


@app.get("/api/v1/iam/context")
def iam_context(_user=Depends(current_user)):
    return _user


@app.post("/api/v1/iam/switch/{organization_id}")
def switch_organization(organization_id: str, _user=Depends(current_user)):
    try:
        enriched = iam.context(auth.get_user(_user["username"]), organization_id)
    except PermissionError as error:
        raise HTTPException(403, str(error)) from error
    if enriched["organization_id"] != organization_id:
        raise HTTPException(403, "You are not a member of this organization")
    return {"access_token": security.issue(enriched), "user": enriched}


@app.post("/api/v1/iam/organizations")
def create_organization(request: OrganizationRequest, _user=Depends(current_user)):
    if not request.name.strip():
        raise HTTPException(422, "Organization name is required")
    organization = iam.create_organization(_user["username"], request.name)
    enriched = iam.context(auth.get_user(_user["username"]), organization["organization_id"])
    return {"organization": organization, "access_token": security.issue(enriched)}


@app.get("/api/v1/iam/members")
def organization_members(_user=Depends(current_user)):
    if _user["organization_role"] not in {"Owner", "Admin"}:
        raise HTTPException(403, "Organization administrator access required")
    return iam.list_members(_user["organization_id"])


@app.patch("/api/v1/iam/members/{username}")
def update_membership(username: str, request: MembershipRequest, _user=Depends(current_user)):
    if _user["organization_role"] not in {"Owner", "Admin"}:
        raise HTTPException(403, "Organization administrator access required")
    if request.role == "Owner" and _user["organization_role"] != "Owner":
        raise HTTPException(403, "Only an Owner can assign Owner access")
    try:
        iam.update_member(_user["organization_id"], username, request.role, request.status, _user["username"])
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    return {"updated": True}


@app.post("/api/v1/iam/invitations")
def create_invitation(request: InvitationRequest, _user=Depends(current_user)):
    if _user["organization_role"] not in {"Owner", "Admin"}:
        raise HTTPException(403, "Organization administrator access required")
    try:
        return iam.invite(_user["organization_id"], request.email, request.role, _user["username"])
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


def _records(organization_id: str):
    return server_inventory.load(include_disabled=True, organization_id=organization_id)


@app.get("/api/v1/decommission-inventory")
def decommission_records(_user=Depends(current_user)):
    organization_id = _user["organization_id"]
    for record in _records(organization_id):
        if str(record.get("status") or "").lower() in decommission_inventory.OFF_STATES:
            decommission_inventory.register_from_server(record, requester="Inventory synchronization", organization_id=organization_id)
    return decommission_inventory.list_records(organization_id=organization_id)


@app.get("/api/v1/dashboard/summary")
def dashboard_summary(_user=Depends(current_user)):
    records = [row for row in _records(_user["organization_id"]) if row.get("enabled", True)]
    on = {"running", "active", "on", "poweredon", "powered on"}
    off = {"stopped", "deallocated", "off", "poweredoff", "powered off"}
    status = [str(row.get("status", "")).lower() for row in records]
    providers = {name: sum(row.get("vm_type") == name for row in records) for name in ("aws", "azure", "vmware")}
    return {
        "total": len(records), "powered_on": sum(value in on for value in status),
        "powered_off": sum(value in off for value in status),
        "unknown": sum(value not in on | off for value in status),
        "production": sum(str(row.get("environment", "")).lower() in {"prod", "production"} for row in records),
        "test": sum(str(row.get("environment", "")).lower() in {"test", "testing", "qa", "uat"} for row in records),
        "providers": providers,
    }


@app.get("/api/v1/inventory/servers")
def inventory(_user=Depends(current_user)):
    safe_fields = ("server_name", "status", "vm_type", "environment", "os_type", "ip_address", "public_ip_address",
                   "private_ip_address", "aws_instance_id", "aws_region", "application", "application_team", "enabled",
                   "os_version", "server_team", "monitoring_service", "important_services", "tags", "gateway_ip",
                   "remote_port", "notes", "private_dns_name", "public_dns_name", "host_name", "instance_type",
                   "architecture", "availability_zone", "vpc_id", "subnet_id", "storage_volumes")
    return [{key: row.get(key) for key in safe_fields} for row in _records(_user["organization_id"])]


@app.get("/api/v1/agents/health")
def agents(_user=Depends(current_user)):
    return health_status.display_rows()


@app.get("/api/v1/hardware/dashboard")
def hardware_dashboard(_user=Depends(current_user)):
    return hardware_monitoring.dashboard()


@app.post("/api/v1/hardware/scan")
def hardware_scan(_user=Depends(current_user)):
    return hardware_monitoring.scan(_user["username"])


@app.post("/api/v1/hardware/tickets")
def hardware_ticket(request: HardwareTicketRequest, _user=Depends(current_user)):
    try:
        return hardware_monitoring.request_ticket(request.alert_index, _user["username"])
    except ValueError as error:
        raise HTTPException(404, str(error)) from error


@app.post("/api/v1/hardware/reports/daily")
def hardware_daily_report(_user=Depends(current_user)):
    return hardware_monitoring.send_daily_report(_user["username"])


@app.post("/api/v1/hardware/tickets/{request_id}/approve")
def approve_hardware_ticket(request_id: str, _user=Depends(current_user)):
    if _user.get("role") not in {"Admin", "Approver"} and _user.get("organization_role") not in {"Owner", "Admin", "Approver"}:
        raise HTTPException(403, "Approver access required")
    try:
        return hardware_monitoring.approve_ticket(request_id, _user["username"])
    except ValueError as error:
        raise HTTPException(404, str(error)) from error


@app.get("/api/v1/usage/summary")
def usage(hours: int = 24, _user=Depends(current_user)):
    if _user.get("role") != "Admin":
        raise HTTPException(403, "Admin access required")
    return ai_usage.summary(max(1, min(hours, 876000)), _user["organization_id"])


@app.get("/api/v1/usage/events")
def usage_events(hours: int = 168, limit: int = 500, _user=Depends(current_user)):
    if _user.get("role") != "Admin":
        raise HTTPException(403, "Admin access required")
    return ai_usage.recent(max(1, min(limit, 5000)), hours=max(1, min(hours, 876000)), organization_id=_user["organization_id"])


@app.get("/api/v1/usage/breakdown")
def usage_breakdown(hours: int = 720, _user=Depends(current_user)):
    if _user.get("role") != "Admin":
        raise HTTPException(403, "Admin access required")
    return ai_usage.breakdown(max(1, min(hours, 876000)), _user["organization_id"])


@app.get("/api/v1/alerts/slack")
def slack_alerts(hours: int = 24, _user=Depends(current_user)):
    org = _user["organization_id"]
    return {"summary": alert_metrics.summary(hours, org), "events": alert_metrics.recent_alerts(hours, 200, org)}


@app.get("/api/v1/alerts/gmail")
def gmail_alerts(hours: int = 24, _user=Depends(current_user)):
    org = _user["organization_id"]
    return {"summary": email_metrics.summary(hours, org), "events": email_metrics.recent_messages(hours, 200, org)}


@app.get("/api/v1/logs")
def logs(component: str = "all", level: str = "all", limit: int = 250, _user=Depends(current_user)):
    return ops_log.recent(component=component, level=level, limit=max(1, min(limit, 1000)), organization_id=_user["organization_id"])


@app.get("/api/v1/chat/sessions")
def chat_sessions(_user=Depends(current_user)):
    return chat_store.sessions(_user["username"], organization_id=_user["organization_id"])


@app.post("/api/v1/chat/sessions")
def create_chat(_user=Depends(current_user)):
    session_id = chat_store.create(_user["username"], organization_id=_user["organization_id"])
    return {"session_id": session_id}


@app.get("/api/v1/chat/sessions/{session_id}")
def chat_messages(session_id: str, _user=Depends(current_user)):
    return chat_store.messages(session_id, _user["username"], _user["organization_id"])


@app.delete("/api/v1/chat/sessions/{session_id}")
def delete_chat(session_id: str, _user=Depends(current_user)):
    chat_store.delete(session_id, _user["username"], _user["organization_id"])
    return {"deleted": True}


@app.post("/api/v1/chat/messages")
def send_chat(request: ChatRequest, _user=Depends(current_user)):
    owned = {item["session_id"] for item in chat_store.sessions(_user["username"], 100, _user["organization_id"])}
    if request.session_id not in owned:
        raise HTTPException(404, "Conversation not found")
    message = request.message.strip()
    if not message:
        raise HTTPException(422, "Message is required")
    history = chat_store.messages(request.session_id, _user["username"], _user["organization_id"])
    chat_store.append(request.session_id, "user", message, _user["username"], _user["organization_id"])
    attachment_context = []
    for item in request.attachments[:5]:
        name = str(item.get("name") or "attachment")[:200]
        content = str(item.get("content") or "")[:50000]
        attachment_context.append(f"Attachment: {name}\n{content}")
    model_message = message
    if attachment_context:
        model_message += "\n\nUser-provided attachments:\n" + "\n\n".join(attachment_context)
    approval_id = chat_operations.parse_approval(message)
    if approval_id:
        answer = chat_operations.approve(
            approval_id, request.session_id, _user,
            authorized=auth.can_cloud_action,
        )
    elif chat_operations.is_operation(message):
        answer = chat_operations.request_operation(
            message, request.session_id, _user["username"]
        )
    else:
        answer = agent.answer_infrastructure_question(
            model_message, inventory_records=_records(_user["organization_id"]), conversation_history=history,
            requester=_user["username"], persona=request.persona, organization_id=_user["organization_id"],
        )
    chat_store.append(request.session_id, "assistant", answer, _user["username"], _user["organization_id"])
    chat_store.set_persona(request.session_id, request.persona, _user["username"], _user["organization_id"])
    ops_log.write(
        "chat", "INFO", "response_completed",
        f"session={request.session_id}; requester={_user['username']}",
        request.session_id, _user["organization_id"],
    )
    return {"role": "assistant", "content": answer}


@app.post("/api/v1/chat/terminations/{request_id}/approve")
def approve_chat_termination(request_id: str, request: TerminationApprovalRequest, _user=Depends(current_user)):
    if _user.get("role") != "Admin":
        raise HTTPException(403, "Admin access is required for termination")
    if not auth.mfa_status(_user["username"])["enabled"]:
        raise HTTPException(403, "Enable MFA under Account & access before terminating infrastructure")
    if not auth.verify_mfa(_user["username"], request.mfa_code):
        raise HTTPException(403, "Invalid or expired authenticator code")
    if not request.backup_confirmed:
        raise HTTPException(422, "Confirm that the required backup or snapshot is complete")
    result = chat_operations.approve_termination(request_id.upper(), request.session_id, _user, auth.can_cloud_action)
    if not result.get("success"):
        raise HTTPException(400, result.get("message") or "Termination failed")
    return result


@app.get("/api/v1/operations/aws/audit")
def aws_audit(hours: int = 168, _user=Depends(current_user)):
    org = _user["organization_id"]
    return {"summary": aws.audit_summary(hours, org), "events": aws.audit_recent(hours, 250, org)}


@app.get("/api/v1/operations/aws/instances/{instance_id}/status")
def aws_instance_status(instance_id: str, region: str | None = None, _user=Depends(current_user)):
    try:
        credentials = credential_store.resolve_provider(_user["organization_id"], "aws")
        return aws.instance_status(instance_id, region, client=aws.client_for_credentials(credentials, region))
    except Exception as error:
        raise HTTPException(400, f"AWS instance status failed: {type(error).__name__}: {error}") from error


@app.post("/api/v1/connections/aws/test")
def test_aws_connection(_user=Depends(current_user)):
    try:
        credentials = credential_store.resolve_provider(_user["organization_id"], "aws")
        result = aws.connection_status(credentials)
        credential_store.record_test(_user["organization_id"], "aws", True)
        return result
    except Exception as error:
        credential_store.record_test(_user["organization_id"], "aws", False, f"{type(error).__name__}: {error}")
        raise HTTPException(400, f"AWS connection failed: {type(error).__name__}: {error}") from error


@app.get("/api/v1/connections/aws/status")
def aws_connection_sync_status(_user=Depends(current_user)):
    return aws.inventory_status()


@app.post("/api/v1/connections/aws/sync")
def sync_aws_inventory(_user=Depends(current_user)):
    try:
        credentials = credential_store.resolve_provider(_user["organization_id"], "aws")
        records = aws.sync_inventory(organization_id=_user["organization_id"], credentials=credentials)
        return {"synchronized": len(records), "status": aws.inventory_status()}
    except Exception as error:
        raise HTTPException(400, f"AWS inventory sync failed: {type(error).__name__}: {error}") from error


@app.post("/api/v1/operations/aws/execute")
def aws_execute(request: AwsOperationRequest, _user=Depends(require_permission(authorization.OPERATE))):
    if not auth.can_cloud_action(request.action, _user):
        raise HTTPException(403, "Your role cannot perform this operation")
    expected = f"CONFIRM {request.action.upper()} {request.identifier}"
    if request.confirmation.strip() != expected:
        raise HTTPException(422, f"Type exactly: {expected}")
    credentials = credential_store.resolve_provider(_user["organization_id"], "aws")
    result = aws.execute(
        request.action, request.identifier, approved=True,
        actor=f"enterprise-api:{_user['username']}", requester=_user["username"],
        approver=_user["username"], source="enterprise_api", region=request.region,
        instance_type=request.instance_type, volume_id=request.volume_id,
        size_gib=request.size_gib, network_interface_id=request.network_interface_id,
        snapshot_id=request.snapshot_id,
        client=aws.client_for_credentials(credentials, request.region),
    )
    if not result.get("success"):
        raise HTTPException(400, result.get("error") or "AWS operation failed")
    return result


@app.post("/api/v1/operations/aws/provision/preview")
def aws_provision_preview(request: AwsProvisionRequest, _user=Depends(require_permission(authorization.OPERATE))):
    if not auth.can_cloud_action("provision_instance", _user):
        raise HTTPException(403, "Your role cannot request AWS provisioning")
    try:
        credentials = credential_store.resolve_provider(_user["organization_id"], "aws")
        return aws.preview_provision(request.model_dump(exclude={"confirmation"}), request.region, client=aws.client_for_credentials(credentials, request.region))
    except Exception as error:
        raise HTTPException(400, f"Provisioning validation failed: {error}") from error


@app.get("/api/v1/operations/aws/provision/options")
def aws_provision_options(region: str = "us-east-1", _user=Depends(require_permission(authorization.OPERATE))):
    if not auth.can_cloud_action("provision_instance", _user):
        raise HTTPException(403, "Your role cannot request AWS provisioning")
    try:
        credentials = credential_store.resolve_provider(_user["organization_id"], "aws")
        return aws.provisioning_options(region, client=aws.client_for_credentials(credentials, region))
    except Exception as error:
        raise HTTPException(400, f"Unable to load AWS provisioning options: {error}") from error


@app.post("/api/v1/operations/aws/provision/execute")
def aws_provision_execute(request: AwsProvisionRequest, _user=Depends(require_permission(authorization.OPERATE))):
    if not auth.can_cloud_action("provision_instance", _user):
        raise HTTPException(403, "Your role cannot provision AWS resources")
    expected = f"APPROVE PROVISION {request.name}"
    if request.confirmation.strip() != expected:
        raise HTTPException(422, f"Type exactly: {expected}")
    credentials = credential_store.resolve_provider(_user["organization_id"], "aws")
    result = aws.provision_instance(request.model_dump(exclude={"confirmation"}), approved=True,
        actor=f"enterprise-api:{_user['username']}", requester=_user["username"],
        approver=_user["username"], source="enterprise_api", region=request.region,
        client=aws.client_for_credentials(credentials, request.region))
    if not result.get("success"):
        raise HTTPException(400, result.get("error") or "AWS provisioning failed")
    return result


@app.get("/api/v1/operations/ssm/status")
def ssm_operation_status(_user=Depends(current_user)):
    return {
        "dry_run": config.SSM_OPERATIONS_DRY_RUN,
        "document_prefix": config.SSM_DOCUMENT_PREFIX,
        "allowed_actions": sorted(config.SSM_ALLOWED_ACTIONS),
    }


@app.get("/api/v1/operations/ssm/audit")
def ssm_audit(limit: int = 500, _user=Depends(current_user)):
    return ssm_operations.audit_recent(max(1, min(limit, 1000)))


@app.get("/api/v1/sccm/status")
def sccm_status(_user=Depends(current_user)):
    return sccm_operations.status()


@app.get("/api/v1/sccm/inventory")
def sccm_inventory(refresh: bool = False, _user=Depends(current_user)):
    try:
        return sccm_operations.inventory(force=refresh)
    except Exception as error:
        if "AccessDenied" in str(error):
            raise HTTPException(403, f"AWS identity lacks permission for the SCCM SSM connector: {error}") from error
        raise HTTPException(502, f"SCCM inventory failed: {type(error).__name__}: {error}") from error


@app.get("/api/v1/sccm/audit")
def sccm_audit(limit: int = 500, _user=Depends(current_user)):
    return ops_log.recent(component="sccm", limit=max(1, min(limit, 1000)), organization_id=_user["organization_id"])


@app.get("/api/v1/sccm/patch-cycles")
def sccm_patch_cycles(_user=Depends(current_user)):
    return sccm_patch_pipeline.list_cycles(_user["organization_id"])


@app.get("/api/v1/sccm/patch-cycles/{cycle_id}")
def sccm_patch_cycle(cycle_id: str, _user=Depends(current_user)):
    try:
        return sccm_patch_pipeline.get(cycle_id, _user["organization_id"])
    except KeyError as error:
        raise HTTPException(404, "Patch cycle not found") from error


@app.post("/api/v1/sccm/patch-cycles")
def create_sccm_patch_cycle(request: SccmPatchCycleRequest, _user=Depends(require_permission(authorization.OPERATE))):
    try:
        return sccm_patch_pipeline.create(request.model_dump(), _user["username"], _user["organization_id"])
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.post("/api/v1/sccm/patch-cycles/{cycle_id}/advance")
def advance_sccm_patch_cycle(cycle_id: str, request: SccmStageRequest, _user=Depends(require_permission(authorization.OPERATE))):
    try:
        return sccm_patch_pipeline.advance(cycle_id, _user["username"], request.evidence, _user["organization_id"])
    except KeyError as error:
        raise HTTPException(404, "Patch cycle not found") from error
    except PermissionError as error:
        raise HTTPException(403, str(error)) from error


@app.post("/api/v1/sccm/patch-cycles/{cycle_id}/approve")
def approve_sccm_patch_cycle(cycle_id: str, _user=Depends(require_permission(authorization.APPROVE))):
    try:
        return sccm_patch_pipeline.approve(cycle_id, _user["username"], _user["organization_id"])
    except (KeyError, ValueError) as error:
        raise HTTPException(422, str(error)) from error


@app.get("/api/v1/sccm/patch-cycles/{cycle_id}/compliance")
def sccm_patch_compliance(cycle_id: str, _user=Depends(current_user)):
    try:
        return sccm_patch_pipeline.compliance(cycle_id, _user["organization_id"])
    except KeyError as error:
        raise HTTPException(404, "Patch cycle not found") from error


@app.post("/api/v1/operations/ssm/execute")
def ssm_execute(request: SsmOperationRequest, _user=Depends(require_permission(authorization.OPERATE))):
    action = ssm_operations.normalize_action(request.action)
    expected = f"CONFIRM {action.upper()} {request.instance_id}"
    if request.confirmation.strip() != expected:
        raise HTTPException(422, f"Type exactly: {expected}")
    try:
        result = ssm_operations.execute(
            action, request.instance_id, parameters=request.parameters,
            region=request.region, approved=True,
            actor=f"enterprise-api:{_user['username']}",
        )
    except PermissionError as error:
        raise HTTPException(403, str(error)) from error
    except Exception as error:
        if "AccessDenied" in str(error):
            raise HTTPException(403, f"AWS identity lacks required SSM permission: {error}. The active AWS_PROFILE or assumed role must allow DescribeInstanceInformation, approved OpsAgent document execution, and command result retrieval.") from error
        raise HTTPException(400, f"SSM operation failed: {type(error).__name__}: {error}") from error
    if not result.get("success"):
        raise HTTPException(400, result.get("stderr") or "SSM operation failed")
    return result


@app.get("/api/v1/operations/{provider}/inventory")
def provider_inventory(provider: str, _user=Depends(current_user)):
    provider = provider.lower()
    if provider not in {"aws", "azure", "vmware"}:
        raise HTTPException(404, "Unknown provider")
    return [row for row in _records(_user["organization_id"]) if row.get("vm_type") == provider]


@app.get("/api/v1/operations/vmware/audit")
def vmware_audit(hours: int = 168, _user=Depends(current_user)):
    org = _user["organization_id"]
    return {"summary": vmware_operations.audit_summary(hours, org), "events": vmware_operations.audit_recent(hours, 250, org)}


@app.post("/api/v1/operations/vmware/execute")
def vmware_execute(request: VMwareOperationRequest, _user=Depends(current_user)):
    if not auth.can_cloud_action(request.action, _user):
        raise HTTPException(403, "Your role cannot perform this operation")
    expected = f"CONFIRM {request.action.upper()} {request.target}"
    if request.confirmation.strip() != expected:
        raise HTTPException(422, f"Type exactly: {expected}")
    result = vmware_operations.execute(
        request.action, request.target, approved=True,
        actor=f"enterprise-api:{_user['username']}", source="enterprise_api",
        requester=_user["username"], approver=_user["username"], **request.parameters,
    )
    if not result.get("success"):
        raise HTTPException(400, result.get("error") or "VMware operation failed")
    return result


@app.get("/api/v1/access/users")
def users(_user=Depends(current_user)):
    if _user.get("role") != "Admin":
        raise HTTPException(403, "Admin access required")
    return auth.list_users()


@app.patch("/api/v1/access/users/{username}")
def update_user(username: str, request: UserUpdateRequest, _user=Depends(current_user)):
    if _user.get("role") != "Admin":
        raise HTTPException(403, "Admin access required")
    auth.update_user(username, role=request.role, enabled=request.enabled, actor=_user["username"])
    return {"updated": True}


@app.get("/api/v1/access/audit")
def access_audit(_user=Depends(current_user)):
    if _user.get("role") != "Admin":
        raise HTTPException(403, "Admin access required")
    return auth.user_audit_recent(500)


@app.post("/api/v1/access/password")
def change_password(request: PasswordRequest, _user=Depends(current_user)):
    verified, error = auth.authenticate(_user["username"], request.current_password)
    if not verified:
        raise HTTPException(400, error or "Current password is incorrect")
    auth.reset_password(_user["username"], request.new_password, actor=_user["username"])
    return {"updated": True}


@app.get("/api/v1/public/integrations/catalog")
def public_integration_catalog():
    return integration_store.catalog()


@app.get("/api/v1/integrations/catalog")
def integration_catalog(_user=Depends(current_user)):
    return integration_store.catalog()


@app.get("/api/v1/integrations/connections")
def integration_connections(_user=Depends(current_user)):
    return integration_store.list_connections(_user["organization_id"])


@app.get("/api/v1/integrations/readiness")
def integration_readiness(_user=Depends(current_user)):
    return connector_readiness.get_readiness(_user["organization_id"])


@app.post("/api/v1/integrations/connections", status_code=201)
def create_integration_connection(request: IntegrationConnectionRequest, _user=Depends(require_permission(authorization.MANAGE_CONNECTORS))):
    if request.connection_type == "api" and not request.credential_reference:
        raise HTTPException(422, "A secret-vault credential reference is required; raw credentials are not accepted")
    try:
        return integration_store.create_connection(
            _user["organization_id"], _user["username"], request.provider,
            request.display_name, request.connection_type, request.endpoint,
            request.credential_reference, request.configuration,
        )
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.post("/api/v1/integrations/connections/secure", status_code=201)
def create_secure_integration_connection(request: SecureIntegrationConnectionRequest, _user=Depends(require_permission(authorization.MANAGE_CONNECTORS))):
    try:
        return credential_store.create_connection(
            _user["organization_id"], _user["username"], request.provider,
            request.display_name, "api", request.endpoint, request.configuration,
            {key: value.get_secret_value() for key, value in request.credentials.items()},
        )
    except credential_store.CredentialVaultUnavailable as error:
        raise HTTPException(503, str(error)) from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.get("/api/v1/integrations/credentials")
def integration_credentials(_user=Depends(require_permission(authorization.MANAGE_CONNECTORS))):
    return credential_store.list_credentials(_user["organization_id"])


@app.get("/api/v1/connections/aws/configuration")
def aws_configuration(_user=Depends(require_permission(authorization.MANAGE_CONNECTORS))):
    credentials = credential_store.resolve_provider(_user["organization_id"], "aws")
    if not credentials:
        raise HTTPException(404, "AWS connection is not configured")
    return {"region": credentials.get("region") or "us-east-2"}


@app.put("/api/v1/connections/aws/configuration")
def update_aws_configuration(request: AwsConfigurationRequest, _user=Depends(require_permission(authorization.MANAGE_CONNECTORS))):
    try:
        credential_store.update_provider_fields(
            _user["organization_id"], _user["username"], "aws", {"region": request.region}
        )
        return {"region": request.region, "updated": True}
    except KeyError as error:
        raise HTTPException(404, "AWS connection is not configured") from error


@app.post("/api/v1/connections/aws/disconnect")
def disconnect_aws(_user=Depends(require_permission(authorization.MANAGE_CONNECTORS))):
    return credential_store.disconnect_provider(
        _user["organization_id"], _user["username"], "aws"
    )


@app.delete("/api/v1/connections/aws")
def delete_aws(_user=Depends(require_permission(authorization.MANAGE_CONNECTORS))):
    result = credential_store.delete_provider(
        _user["organization_id"], _user["username"], "aws"
    )
    # Remove the disconnected provider's current discovery cache. Immutable
    # operation and organization audit evidence is intentionally retained.
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM ops_agent.aws_ec2_inventory WHERE organization_id=%s", (_user["organization_id"],))
            cursor.execute("DELETE FROM ops_agent.server_inventory WHERE organization_id=%s AND vm_type='aws'", (_user["organization_id"],))
        connection.commit()
    return result


@app.post("/api/v1/integrations/connections/{provider}/test")
def test_tenant_integration(provider: str, _user=Depends(require_permission(authorization.MANAGE_CONNECTORS))):
    provider = provider.lower()
    try:
        credentials = credential_store.resolve_provider(_user["organization_id"], provider)
        if not credentials:
            raise ValueError("Save the connector credentials before testing")
        result = connector_testing.test_provider(provider, credentials)
        credential_store.record_test(_user["organization_id"], provider, True)
        return result
    except ValueError as error:
        credential_store.record_test(_user["organization_id"], provider, False, str(error))
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        credential_store.record_test(_user["organization_id"], provider, False, f"{type(error).__name__}: {error}")
        raise HTTPException(400, f"{provider.title()} connection failed: {type(error).__name__}: {error}") from error


@app.get("/api/v1/gateways")
def customer_gateways(_user=Depends(current_user)):
    return integration_store.list_gateways(_user["organization_id"])


@app.post("/api/v1/gateways/register", status_code=201)
def register_customer_gateway(request: GatewayRegistrationRequest, _user=Depends(require_permission(authorization.MANAGE_CONNECTORS))):
    return integration_store.create_gateway(
        _user["organization_id"], _user["username"], request.name, request.platform,
    )


@app.post("/api/v1/integrations/grafana/register", status_code=201)
def register_grafana_connection(request: GatewayRegistrationRequest, http_request: Request, _user=Depends(require_permission(authorization.MANAGE_CONNECTORS))):
    return grafana_connector.register(
        _user["organization_id"], _user["username"], request.name, str(http_request.base_url),
    )


@app.get("/api/v1/integrations/grafana")
def grafana_connections(_user=Depends(current_user)):
    return grafana_connector.list_connectors(_user["organization_id"])


@app.post("/api/v1/public/integrations/grafana/{connector_id}/events", status_code=202)
async def receive_grafana_event(connector_id: str, request: Request, authorization: str | None = Header(default=None)):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Grafana webhook bearer token is required")
    try:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise ValueError("Payload must be a JSON object")
        return grafana_connector.receive(connector_id, authorization.split(" ", 1)[1], payload)
    except PermissionError as error:
        raise HTTPException(401, str(error)) from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.post("/api/v1/integrations/monitoring/{provider}/register", status_code=201)
def register_monitoring_connection(provider: str, request: GatewayRegistrationRequest, http_request: Request, _user=Depends(require_permission(authorization.MANAGE_CONNECTORS))):
    try:
        return monitoring_connectors.register(
            _user["organization_id"], _user["username"], provider, request.name, str(http_request.base_url),
        )
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.post("/api/v1/public/integrations/monitoring/{provider}/{connector_id}/events", status_code=202)
async def receive_monitoring_event(provider: str, connector_id: str, request: Request, authorization: str | None = Header(default=None)):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Monitoring webhook bearer token is required")
    try:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise ValueError("Payload must be a JSON object")
        return monitoring_connectors.receive(provider, connector_id, authorization.split(" ", 1)[1], payload)
    except PermissionError as error:
        raise HTTPException(401, str(error)) from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.get("/api/v1/settings")
def get_settings(_user=Depends(current_user)):
    return settings_store.get(_user["username"])


@app.put("/api/v1/settings")
def update_settings(request: SettingsRequest, _user=Depends(current_user)):
    if request.theme not in {"dark", "light", "system"}:
        raise HTTPException(422, "Unsupported theme")
    if request.font_size not in {"compact", "comfortable", "large"}:
        raise HTTPException(422, "Unsupported font size")
    if request.density not in {"compact", "comfortable"}:
        raise HTTPException(422, "Unsupported density")
    allowed_extensions = {"aws", "azure", "vmware", "sccm", "intune", "ivanti", "jira", "servicenow", "slack", "gmail", "grafana", "hardware"}
    values = request.model_dump()
    values["extensions"] = {key: bool(value) for key, value in request.extensions.items() if key in allowed_extensions}
    return settings_store.save(_user["username"], values)


# In production the React build is copied into the API image. Mount it last so
# every /api route keeps precedence while the root serves the OpsAgent UI.
_frontend_dist = Path(__file__).resolve().parents[1] / "frontend" / "dist"
if _frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="frontend")

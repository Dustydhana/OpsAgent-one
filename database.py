"""Shared PostgreSQL connection helpers for all persistent state."""

import threading
import time
import config

try:
    import psycopg
except ImportError:
    psycopg = None


_INITIALIZED = False
_INITIALIZE_LOCK = threading.Lock()


def connect(*, row_factory=None, attempts=4):
    if psycopg is None:
        raise RuntimeError("psycopg is required; install the project requirements")
    if not config.DATABASE_URL:
        raise RuntimeError("DATABASE_URL is required; local persistence is disabled")
    kwargs = {"connect_timeout": 5}
    if row_factory is not None:
        kwargs["row_factory"] = row_factory
    connection = None
    last_error = None
    for attempt in range(max(1, int(attempts))):
        try:
            connection = psycopg.connect(config.DATABASE_URL, **kwargs)
            break
        except psycopg.OperationalError as error:
            last_error = error
            if attempt + 1 >= max(1, int(attempts)):
                raise
            # PostgreSQL crash recovery on the local Windows service normally
            # lasts less than a second. A bounded backoff prevents transient
            # recovery/startup windows from becoming user-visible HTTP 500s.
            time.sleep(min(0.25 * (2 ** attempt), 2.0))
    if connection is None:
        raise last_error or RuntimeError("Unable to connect to PostgreSQL")
    with connection.cursor() as cursor:
        cursor.execute("CREATE SCHEMA IF NOT EXISTS ops_agent")
    connection.commit()
    return connection


def initialize():
    """Create all application-owned tables without deleting existing data."""
    global _INITIALIZED
    if _INITIALIZED:
        return
    with _INITIALIZE_LOCK:
        if _INITIALIZED:
            return
        _initialize_once()
        _INITIALIZED = True


def _initialize_once():
    """Perform idempotent schema setup once per application process."""
    statements = [
        """CREATE TABLE IF NOT EXISTS ops_agent.server_inventory (
            server_name TEXT PRIMARY KEY, ip_address TEXT NOT NULL UNIQUE,
            public_ip_address TEXT, private_ip_address TEXT, status TEXT NOT NULL DEFAULT 'active',
            enabled BOOLEAN NOT NULL DEFAULT TRUE, vm_type TEXT NOT NULL DEFAULT 'unknown',
            environment TEXT NOT NULL DEFAULT 'unknown', os_type TEXT NOT NULL DEFAULT 'auto',
            os_version TEXT NOT NULL DEFAULT 'Unknown', application TEXT NOT NULL DEFAULT 'Unknown',
            application_team TEXT NOT NULL DEFAULT 'Unknown', application_team_email TEXT,
            server_team TEXT NOT NULL DEFAULT 'Unknown', monitoring_service TEXT,
            important_services TEXT[] NOT NULL DEFAULT '{}', tags TEXT[] NOT NULL DEFAULT '{}',
            aliases TEXT[] NOT NULL DEFAULT '{}', gateway_ip TEXT, remote_username TEXT,
            remote_port INTEGER NOT NULL DEFAULT 22, remote_key_path TEXT,
            aws_instance_id TEXT, aws_region TEXT, private_dns_name TEXT, public_dns_name TEXT,
            host_name TEXT, instance_type TEXT, architecture TEXT, availability_zone TEXT,
            vpc_id TEXT, subnet_id TEXT, storage_volumes JSONB NOT NULL DEFAULT '[]'::jsonb,
            notes TEXT NOT NULL DEFAULT '')""",
        """CREATE TABLE IF NOT EXISTS ops_agent.decommission_inventory (
            server_name TEXT PRIMARY KEY, provider TEXT NOT NULL DEFAULT 'unknown',
            resource_id TEXT, ip_address TEXT, power_state TEXT NOT NULL,
            lifecycle_state TEXT NOT NULL DEFAULT 'scream_test', owner TEXT NOT NULL DEFAULT 'Unknown',
            requested_by TEXT, ticket_reference TEXT, reason TEXT NOT NULL DEFAULT 'Power state discovered by inventory',
            scream_test_started_at TIMESTAMPTZ, scream_test_ends_at TIMESTAMPTZ,
            decommissioned_at TIMESTAMPTZ, source TEXT NOT NULL DEFAULT 'server_inventory',
            details JSONB NOT NULL DEFAULT '{}'::jsonb, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""",
        """CREATE TABLE IF NOT EXISTS ops_agent.aws_ec2_inventory (
            region TEXT NOT NULL, instance_id TEXT NOT NULL, account_id TEXT,
            name TEXT, state TEXT NOT NULL, instance_type TEXT, platform_details TEXT,
            architecture TEXT, image_id TEXT, launch_time TIMESTAMPTZ,
            availability_zone TEXT, vpc_id TEXT, vpc_name TEXT, vpc_cidr TEXT,
            subnet_id TEXT, subnet_name TEXT, subnet_cidr TEXT,
            private_ip TEXT, public_ip TEXT, private_dns TEXT, public_dns TEXT,
            key_name TEXT, key_fingerprint TEXT, iam_instance_profile_arn TEXT,
            security_group_ids TEXT[] NOT NULL DEFAULT '{}',
            security_group_names TEXT[] NOT NULL DEFAULT '{}',
            volume_ids TEXT[] NOT NULL DEFAULT '{}', volume_details JSONB NOT NULL DEFAULT '[]'::jsonb,
            network_interface_ids TEXT[] NOT NULL DEFAULT '{}', ssm_computer_name TEXT,
            ssm_platform_name TEXT, ssm_platform_version TEXT, ssm_ping_status TEXT, ssm_agent_version TEXT,
            tags TEXT[] NOT NULL DEFAULT '{}', discovered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), PRIMARY KEY (region,instance_id))""",
        """CREATE TABLE IF NOT EXISTS ops_agent.component_health (
            component TEXT PRIMARY KEY, status TEXT NOT NULL, details TEXT NOT NULL DEFAULT '',
            last_heartbeat TIMESTAMPTZ NOT NULL DEFAULT NOW())""",
        """CREATE TABLE IF NOT EXISTS ops_agent.ai_usage_events (
            id BIGSERIAL PRIMARY KEY, occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            requester TEXT NOT NULL DEFAULT 'unknown', activity TEXT NOT NULL,
            request_text TEXT, model TEXT NOT NULL, input_tokens INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0, total_tokens INTEGER NOT NULL DEFAULT 0,
            estimated_cost_usd NUMERIC(14,8) NOT NULL DEFAULT 0, success BOOLEAN NOT NULL,
            error_message TEXT)""",
        """CREATE TABLE IF NOT EXISTS ops_agent.chat_sessions (
            session_id TEXT PRIMARY KEY, requester TEXT NOT NULL, title TEXT NOT NULL DEFAULT 'New chat',
            persona TEXT NOT NULL DEFAULT 'Senior Infrastructure Architect', created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""",
        """CREATE TABLE IF NOT EXISTS ops_agent.chat_messages (
            id BIGSERIAL PRIMARY KEY, session_id TEXT NOT NULL REFERENCES ops_agent.chat_sessions(session_id) ON DELETE CASCADE,
            role TEXT NOT NULL, content TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""",
        """CREATE TABLE IF NOT EXISTS ops_agent.chat_action_requests (
            request_id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES ops_agent.chat_sessions(session_id) ON DELETE CASCADE,
            status TEXT NOT NULL, requester TEXT NOT NULL, approver TEXT,
            action TEXT NOT NULL, server_name TEXT NOT NULL, provider TEXT NOT NULL,
            resource_id TEXT NOT NULL, region TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            expires_at TIMESTAMPTZ NOT NULL, approved_at TIMESTAMPTZ, executed_at TIMESTAMPTZ,
            before_state TEXT, after_state TEXT, success BOOLEAN, error_message TEXT,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""",
        """CREATE TABLE IF NOT EXISTS ops_agent.metric_samples (
            id BIGSERIAL PRIMARY KEY, recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), host TEXT NOT NULL,
            os_type TEXT NOT NULL, disk_percent DOUBLE PRECISION, memory_percent DOUBLE PRECISION,
            cpu_percent DOUBLE PRECISION)""",
        """CREATE TABLE IF NOT EXISTS ops_agent.alert_events (
            id BIGSERIAL PRIMARY KEY, occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), event TEXT NOT NULL,
            alert_key TEXT, request_mode TEXT, slack_ts TEXT, requester TEXT,
            target_name TEXT, request_text TEXT)""",
        """CREATE TABLE IF NOT EXISTS ops_agent.email_events (
            id BIGSERIAL PRIMARY KEY, occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            event TEXT NOT NULL, message_id TEXT, sender TEXT, subject TEXT,
            request_id TEXT, details TEXT)""",
        """CREATE TABLE IF NOT EXISTS ops_agent.operational_logs (
            id BIGSERIAL PRIMARY KEY, occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            component TEXT NOT NULL, level TEXT NOT NULL, event TEXT NOT NULL,
            details TEXT, correlation_id TEXT)""",
        """CREATE TABLE IF NOT EXISTS ops_agent.sccm_patch_cycles (
            cycle_id TEXT PRIMARY KEY, name TEXT NOT NULL, status TEXT NOT NULL,
            current_stage INTEGER NOT NULL DEFAULT 0, release_date DATE NOT NULL,
            test_date TIMESTAMPTZ NOT NULL, production_date TIMESTAMPTZ NOT NULL,
            deadline_date TIMESTAMPTZ NOT NULL, kb_ids TEXT[] NOT NULL DEFAULT '{}',
            software_update_group TEXT NOT NULL, deployment_package TEXT NOT NULL,
            test_collection TEXT NOT NULL, pilot_collection TEXT,
            production_collection TEXT NOT NULL, change_system TEXT NOT NULL,
            change_id TEXT, stakeholder_emails TEXT[] NOT NULL DEFAULT '{}',
            application_emails TEXT[] NOT NULL DEFAULT '{}', approval_status TEXT NOT NULL DEFAULT 'pending',
            approved_by TEXT, approved_at TIMESTAMPTZ, created_by TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb)""",
        """CREATE TABLE IF NOT EXISTS ops_agent.sccm_patch_events (
            id BIGSERIAL PRIMARY KEY, cycle_id TEXT NOT NULL REFERENCES ops_agent.sccm_patch_cycles(cycle_id) ON DELETE CASCADE,
            occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), stage INTEGER NOT NULL,
            stage_code TEXT NOT NULL, status TEXT NOT NULL, actor TEXT NOT NULL,
            details JSONB NOT NULL DEFAULT '{}'::jsonb)""",
        """CREATE TABLE IF NOT EXISTS ops_agent.demo_requests (
            request_id TEXT PRIMARY KEY, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            full_name TEXT NOT NULL, business_email TEXT NOT NULL, company TEXT NOT NULL,
            job_role TEXT, phone TEXT, estate_size TEXT, interests TEXT[] NOT NULL DEFAULT '{}',
            message TEXT, source TEXT NOT NULL DEFAULT 'public-homepage', status TEXT NOT NULL DEFAULT 'new')""",
        """CREATE TABLE IF NOT EXISTS ops_agent.email_action_requests (
            request_id TEXT PRIMARY KEY, status TEXT NOT NULL, requester TEXT NOT NULL, approver TEXT,
            action TEXT NOT NULL, target_identifier TEXT NOT NULL, alert_date TEXT,
            server_name TEXT, ip_address TEXT, original_subject TEXT, root_message_id TEXT,
            expires_at TIMESTAMPTZ, approved_at TIMESTAMPTZ, executed_at TIMESTAMPTZ,
            instance_type TEXT, volume_id TEXT, size_gib INTEGER, network_interface_id TEXT,
            snapshot_id TEXT, description TEXT,
            before_state TEXT, after_state TEXT, success BOOLEAN, verified BOOLEAN,
            dry_run BOOLEAN, error_message TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""",
        """CREATE TABLE IF NOT EXISTS ops_agent.slack_action_requests (
            request_id TEXT PRIMARY KEY, status TEXT NOT NULL,
            requester TEXT NOT NULL, requester_id TEXT NOT NULL,
            approver TEXT, approver_id TEXT,
            action TEXT NOT NULL, server_name TEXT NOT NULL,
            provider TEXT NOT NULL, resource_id TEXT NOT NULL,
            volume_id TEXT, snapshot_id TEXT, description TEXT, region TEXT,
            channel_id TEXT NOT NULL, thread_ts TEXT NOT NULL, source_message_ts TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), expires_at TIMESTAMPTZ NOT NULL,
            approved_at TIMESTAMPTZ, executed_at TIMESTAMPTZ,
            before_state TEXT, after_state TEXT, success BOOLEAN, verified BOOLEAN,
            dry_run BOOLEAN, error_message TEXT,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""",
        """CREATE TABLE IF NOT EXISTS ops_agent.cloud_operation_audit (
            id BIGSERIAL PRIMARY KEY, occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), provider TEXT NOT NULL,
            actor TEXT NOT NULL, action TEXT NOT NULL, target TEXT NOT NULL, approved BOOLEAN NOT NULL,
            dry_run BOOLEAN NOT NULL, success BOOLEAN, instance_id TEXT,
            volume_id TEXT, snapshot_id TEXT, message TEXT, error_message TEXT,
            request_id TEXT, source TEXT NOT NULL DEFAULT 'unknown', requester TEXT,
            approver TEXT, started_at TIMESTAMPTZ, completed_at TIMESTAMPTZ,
            duration_ms BIGINT, before_status TEXT, after_status TEXT, aws_request_id TEXT)""",
        """CREATE TABLE IF NOT EXISTS ops_agent.app_users (
            username TEXT PRIMARY KEY, display_name TEXT NOT NULL, role TEXT NOT NULL,
            password_hash BYTEA NOT NULL, password_salt BYTEA NOT NULL,
            enabled BOOLEAN NOT NULL DEFAULT TRUE, failed_attempts INTEGER NOT NULL DEFAULT 0,
            locked_until TIMESTAMPTZ, last_login_at TIMESTAMPTZ,
            password_changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            created_by TEXT, CONSTRAINT app_users_role_check CHECK (role IN ('Admin','Operator','Viewer')))""",
        """CREATE TABLE IF NOT EXISTS ops_agent.app_user_audit (
            id BIGSERIAL PRIMARY KEY, occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            actor TEXT NOT NULL, action TEXT NOT NULL, target_username TEXT NOT NULL,
            previous_role TEXT, new_role TEXT, details TEXT)""",
        """CREATE TABLE IF NOT EXISTS ops_agent.user_preferences (
            username TEXT PRIMARY KEY REFERENCES ops_agent.app_users(username) ON DELETE CASCADE,
            preferences JSONB NOT NULL DEFAULT '{}'::jsonb,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""",
        """CREATE TABLE IF NOT EXISTS ops_agent.external_identities (
            provider TEXT NOT NULL, subject TEXT NOT NULL,
            username TEXT NOT NULL REFERENCES ops_agent.app_users(username) ON DELETE CASCADE,
            email TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_login_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY(provider,subject))""",
        """CREATE TABLE IF NOT EXISTS ops_agent.organizations (
            organization_id TEXT PRIMARY KEY, name TEXT NOT NULL,
            slug TEXT NOT NULL UNIQUE, created_by TEXT NOT NULL,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""",
        """CREATE TABLE IF NOT EXISTS ops_agent.organization_memberships (
            organization_id TEXT NOT NULL REFERENCES ops_agent.organizations(organization_id) ON DELETE CASCADE,
            username TEXT NOT NULL REFERENCES ops_agent.app_users(username) ON DELETE CASCADE,
            role TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'active',
            joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY(organization_id,username),
            CONSTRAINT organization_role_check CHECK(role IN ('Owner','Admin','Operator','Approver','Viewer','Auditor')),
            CONSTRAINT membership_status_check CHECK(status IN ('active','suspended')) )""",
        """CREATE TABLE IF NOT EXISTS ops_agent.organization_invitations (
            invitation_id TEXT PRIMARY KEY, organization_id TEXT NOT NULL REFERENCES ops_agent.organizations(organization_id) ON DELETE CASCADE,
            email TEXT NOT NULL, role TEXT NOT NULL, token_hash TEXT NOT NULL UNIQUE,
            invited_by TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
            expires_at TIMESTAMPTZ NOT NULL, accepted_by TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), accepted_at TIMESTAMPTZ,
            CONSTRAINT invitation_role_check CHECK(role IN ('Admin','Operator','Approver','Viewer','Auditor')) )""",
        """CREATE TABLE IF NOT EXISTS ops_agent.organization_audit (
            id BIGSERIAL PRIMARY KEY, organization_id TEXT NOT NULL,
            occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), actor TEXT NOT NULL,
            action TEXT NOT NULL, target TEXT, details JSONB NOT NULL DEFAULT '{}'::jsonb)""",
        """CREATE TABLE IF NOT EXISTS ops_agent.integration_connections (
            connection_id TEXT PRIMARY KEY, organization_id TEXT NOT NULL REFERENCES ops_agent.organizations(organization_id) ON DELETE CASCADE,
            provider TEXT NOT NULL, display_name TEXT NOT NULL, connection_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'configured', endpoint TEXT, credential_reference TEXT,
            configuration JSONB NOT NULL DEFAULT '{}'::jsonb, last_tested_at TIMESTAMPTZ,
            last_error TEXT, created_by TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT integration_connection_type_check CHECK(connection_type IN ('api','gateway')),
            CONSTRAINT integration_status_check CHECK(status IN ('configured','connected','attention','disabled')))""",
        """CREATE TABLE IF NOT EXISTS ops_agent.connector_credentials (
            credential_id TEXT PRIMARY KEY, organization_id TEXT NOT NULL REFERENCES ops_agent.organizations(organization_id) ON DELETE CASCADE,
            provider TEXT NOT NULL, name TEXT NOT NULL, encrypted_payload TEXT NOT NULL,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb, status TEXT NOT NULL DEFAULT 'active',
            key_version INTEGER NOT NULL DEFAULT 1, created_by TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT connector_credential_status_check CHECK(status IN ('active','disabled','rotating')))""",
        """CREATE TABLE IF NOT EXISTS ops_agent.customer_gateways (
            gateway_id TEXT PRIMARY KEY, organization_id TEXT NOT NULL REFERENCES ops_agent.organizations(organization_id) ON DELETE CASCADE,
            name TEXT NOT NULL, platform TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
            enrollment_token_hash TEXT NOT NULL, version TEXT, capabilities JSONB NOT NULL DEFAULT '[]'::jsonb,
            last_heartbeat_at TIMESTAMPTZ, created_by TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT gateway_status_check CHECK(status IN ('pending','online','offline','revoked')))""",
        """CREATE TABLE IF NOT EXISTS ops_agent.grafana_connectors (
            connector_id TEXT PRIMARY KEY, organization_id TEXT NOT NULL REFERENCES ops_agent.organizations(organization_id) ON DELETE CASCADE,
            name TEXT NOT NULL, token_hash TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
            last_received_at TIMESTAMPTZ, created_by TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT grafana_connector_status_check CHECK(status IN ('pending','connected','attention','revoked')))""",
        """CREATE TABLE IF NOT EXISTS ops_agent.grafana_events (
            event_id BIGSERIAL PRIMARY KEY, connector_id TEXT NOT NULL REFERENCES ops_agent.grafana_connectors(connector_id) ON DELETE CASCADE,
            organization_id TEXT NOT NULL, event_key TEXT NOT NULL, alert_status TEXT NOT NULL,
            title TEXT NOT NULL, payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), UNIQUE(connector_id,event_key,alert_status))""",
        """CREATE TABLE IF NOT EXISTS ops_agent.monitoring_connectors (
            connector_id TEXT PRIMARY KEY, organization_id TEXT NOT NULL REFERENCES ops_agent.organizations(organization_id) ON DELETE CASCADE,
            provider TEXT NOT NULL, name TEXT NOT NULL, token_hash TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending', last_received_at TIMESTAMPTZ,
            created_by TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""",
        """CREATE TABLE IF NOT EXISTS ops_agent.monitoring_events (
            event_id BIGSERIAL PRIMARY KEY, connector_id TEXT NOT NULL REFERENCES ops_agent.monitoring_connectors(connector_id) ON DELETE CASCADE,
            organization_id TEXT NOT NULL, provider TEXT NOT NULL, event_key TEXT NOT NULL,
            event_status TEXT NOT NULL, title TEXT NOT NULL, payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            received_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""",
        """CREATE TABLE IF NOT EXISTS ops_agent.vmware_endpoints (
            endpoint TEXT PRIMARY KEY, product TEXT NOT NULL, version TEXT, build TEXT,
            api_type TEXT, last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""",
        """CREATE TABLE IF NOT EXISTS ops_agent.vmware_hosts (
            endpoint TEXT NOT NULL REFERENCES ops_agent.vmware_endpoints(endpoint) ON DELETE CASCADE,
            host_name TEXT NOT NULL, connection_state TEXT, power_state TEXT,
            maintenance_mode BOOLEAN NOT NULL DEFAULT FALSE, vendor TEXT, model TEXT,
            cpu_threads INTEGER, memory_gib DOUBLE PRECISION, cpu_usage_mhz INTEGER,
            memory_usage_gib DOUBLE PRECISION, last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (endpoint,host_name))""",
        """CREATE TABLE IF NOT EXISTS ops_agent.vmware_datastores (
            endpoint TEXT NOT NULL REFERENCES ops_agent.vmware_endpoints(endpoint) ON DELETE CASCADE,
            datastore_name TEXT NOT NULL, accessible BOOLEAN, datastore_type TEXT,
            capacity_gib DOUBLE PRECISION, free_gib DOUBLE PRECISION,
            last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (endpoint,datastore_name))""",
        """CREATE TABLE IF NOT EXISTS ops_agent.vmware_networks (
            endpoint TEXT NOT NULL REFERENCES ops_agent.vmware_endpoints(endpoint) ON DELETE CASCADE,
            network_name TEXT NOT NULL, last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (endpoint,network_name))""",
        """CREATE TABLE IF NOT EXISTS ops_agent.vmware_virtual_machines (
            endpoint TEXT NOT NULL REFERENCES ops_agent.vmware_endpoints(endpoint) ON DELETE CASCADE,
            vm_name TEXT NOT NULL, power_state TEXT, guest_os TEXT, cpu_count INTEGER,
            memory_mb INTEGER, tools_status TEXT, ip_address TEXT, snapshot_count INTEGER,
            last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (endpoint,vm_name))""",
        "ALTER TABLE ops_agent.server_inventory ADD COLUMN IF NOT EXISTS remote_key_path TEXT",
        "ALTER TABLE ops_agent.server_inventory ADD COLUMN IF NOT EXISTS private_dns_name TEXT",
        "ALTER TABLE ops_agent.server_inventory ADD COLUMN IF NOT EXISTS public_dns_name TEXT",
        "ALTER TABLE ops_agent.server_inventory ADD COLUMN IF NOT EXISTS host_name TEXT",
        "ALTER TABLE ops_agent.server_inventory ADD COLUMN IF NOT EXISTS instance_type TEXT",
        "ALTER TABLE ops_agent.server_inventory ADD COLUMN IF NOT EXISTS architecture TEXT",
        "ALTER TABLE ops_agent.server_inventory ADD COLUMN IF NOT EXISTS availability_zone TEXT",
        "ALTER TABLE ops_agent.server_inventory ADD COLUMN IF NOT EXISTS vpc_id TEXT",
        "ALTER TABLE ops_agent.server_inventory ADD COLUMN IF NOT EXISTS subnet_id TEXT",
        "ALTER TABLE ops_agent.server_inventory ADD COLUMN IF NOT EXISTS storage_volumes JSONB NOT NULL DEFAULT '[]'::jsonb",
        "ALTER TABLE ops_agent.aws_ec2_inventory ADD COLUMN IF NOT EXISTS volume_details JSONB NOT NULL DEFAULT '[]'::jsonb",
        "ALTER TABLE ops_agent.aws_ec2_inventory ADD COLUMN IF NOT EXISTS ssm_computer_name TEXT",
        "ALTER TABLE ops_agent.aws_ec2_inventory ADD COLUMN IF NOT EXISTS ssm_platform_name TEXT",
        "ALTER TABLE ops_agent.aws_ec2_inventory ADD COLUMN IF NOT EXISTS ssm_platform_version TEXT",
        "ALTER TABLE ops_agent.aws_ec2_inventory ADD COLUMN IF NOT EXISTS ssm_ping_status TEXT",
        "ALTER TABLE ops_agent.aws_ec2_inventory ADD COLUMN IF NOT EXISTS ssm_agent_version TEXT",
        "ALTER TABLE ops_agent.email_action_requests ADD COLUMN IF NOT EXISTS server_name TEXT",
        "ALTER TABLE ops_agent.email_action_requests ADD COLUMN IF NOT EXISTS ip_address TEXT",
        "ALTER TABLE ops_agent.email_action_requests ADD COLUMN IF NOT EXISTS original_subject TEXT",
        "ALTER TABLE ops_agent.email_action_requests ADD COLUMN IF NOT EXISTS root_message_id TEXT",
        "ALTER TABLE ops_agent.email_action_requests ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ",
        "ALTER TABLE ops_agent.email_action_requests ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ",
        "ALTER TABLE ops_agent.email_action_requests ADD COLUMN IF NOT EXISTS executed_at TIMESTAMPTZ",
        "ALTER TABLE ops_agent.email_action_requests ADD COLUMN IF NOT EXISTS instance_type TEXT",
        "ALTER TABLE ops_agent.email_action_requests ADD COLUMN IF NOT EXISTS volume_id TEXT",
        "ALTER TABLE ops_agent.email_action_requests ADD COLUMN IF NOT EXISTS size_gib INTEGER",
        "ALTER TABLE ops_agent.email_action_requests ADD COLUMN IF NOT EXISTS network_interface_id TEXT",
        "ALTER TABLE ops_agent.email_action_requests ADD COLUMN IF NOT EXISTS before_state TEXT",
        "ALTER TABLE ops_agent.email_action_requests ADD COLUMN IF NOT EXISTS after_state TEXT",
        "ALTER TABLE ops_agent.email_action_requests ADD COLUMN IF NOT EXISTS success BOOLEAN",
        "ALTER TABLE ops_agent.email_action_requests ADD COLUMN IF NOT EXISTS verified BOOLEAN",
        "ALTER TABLE ops_agent.email_action_requests ADD COLUMN IF NOT EXISTS dry_run BOOLEAN",
        "ALTER TABLE ops_agent.email_action_requests ADD COLUMN IF NOT EXISTS error_message TEXT",
        "ALTER TABLE ops_agent.email_action_requests ADD COLUMN IF NOT EXISTS snapshot_id TEXT",
        "ALTER TABLE ops_agent.email_action_requests ADD COLUMN IF NOT EXISTS description TEXT",
        "ALTER TABLE ops_agent.cloud_operation_audit ADD COLUMN IF NOT EXISTS success BOOLEAN",
        "ALTER TABLE ops_agent.cloud_operation_audit ADD COLUMN IF NOT EXISTS instance_id TEXT",
        "ALTER TABLE ops_agent.cloud_operation_audit ADD COLUMN IF NOT EXISTS message TEXT",
        "ALTER TABLE ops_agent.cloud_operation_audit ADD COLUMN IF NOT EXISTS error_message TEXT",
        "ALTER TABLE ops_agent.cloud_operation_audit ADD COLUMN IF NOT EXISTS volume_id TEXT",
        "ALTER TABLE ops_agent.cloud_operation_audit ADD COLUMN IF NOT EXISTS snapshot_id TEXT",
        "ALTER TABLE ops_agent.cloud_operation_audit ADD COLUMN IF NOT EXISTS request_id TEXT",
        "ALTER TABLE ops_agent.cloud_operation_audit ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'unknown'",
        "ALTER TABLE ops_agent.cloud_operation_audit ADD COLUMN IF NOT EXISTS requester TEXT",
        "ALTER TABLE ops_agent.cloud_operation_audit ADD COLUMN IF NOT EXISTS approver TEXT",
        "ALTER TABLE ops_agent.cloud_operation_audit ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ",
        "ALTER TABLE ops_agent.cloud_operation_audit ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ",
        "ALTER TABLE ops_agent.cloud_operation_audit ADD COLUMN IF NOT EXISTS duration_ms BIGINT",
        "ALTER TABLE ops_agent.cloud_operation_audit ADD COLUMN IF NOT EXISTS before_status TEXT",
        "ALTER TABLE ops_agent.cloud_operation_audit ADD COLUMN IF NOT EXISTS after_status TEXT",
        "ALTER TABLE ops_agent.cloud_operation_audit ADD COLUMN IF NOT EXISTS aws_request_id TEXT",
        "ALTER TABLE ops_agent.app_users ADD COLUMN IF NOT EXISTS mfa_secret_encrypted TEXT",
        "ALTER TABLE ops_agent.app_users ADD COLUMN IF NOT EXISTS mfa_enabled BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE ops_agent.slack_action_requests ADD COLUMN IF NOT EXISTS volume_id TEXT",
        "ALTER TABLE ops_agent.slack_action_requests ADD COLUMN IF NOT EXISTS snapshot_id TEXT",
        "ALTER TABLE ops_agent.slack_action_requests ADD COLUMN IF NOT EXISTS description TEXT",
        "ALTER TABLE ops_agent.alert_events ADD COLUMN IF NOT EXISTS requester TEXT",
        "ALTER TABLE ops_agent.alert_events ADD COLUMN IF NOT EXISTS target_name TEXT",
        "ALTER TABLE ops_agent.alert_events ADD COLUMN IF NOT EXISTS request_text TEXT",
        "ALTER TABLE ops_agent.server_inventory DROP COLUMN IF EXISTS connection",
        "ALTER TABLE ops_agent.email_action_requests DROP COLUMN IF EXISTS record",
        "ALTER TABLE ops_agent.cloud_operation_audit DROP COLUMN IF EXISTS result",
        "CREATE INDEX IF NOT EXISTS metric_samples_host_time_idx ON ops_agent.metric_samples(host, recorded_at DESC)",
        "CREATE INDEX IF NOT EXISTS alert_events_time_idx ON ops_agent.alert_events(occurred_at DESC)",
        "CREATE INDEX IF NOT EXISTS email_events_time_idx ON ops_agent.email_events(occurred_at DESC)",
        "CREATE INDEX IF NOT EXISTS operational_logs_time_idx ON ops_agent.operational_logs(occurred_at DESC)",
        "CREATE INDEX IF NOT EXISTS operational_logs_component_idx ON ops_agent.operational_logs(component, occurred_at DESC)",
        "CREATE INDEX IF NOT EXISTS sccm_patch_cycles_status_idx ON ops_agent.sccm_patch_cycles(status, production_date)",
        "CREATE INDEX IF NOT EXISTS sccm_patch_events_cycle_idx ON ops_agent.sccm_patch_events(cycle_id, occurred_at DESC)",
        "CREATE INDEX IF NOT EXISTS demo_requests_created_idx ON ops_agent.demo_requests(created_at DESC)",
        "CREATE INDEX IF NOT EXISTS slack_action_requests_time_idx ON ops_agent.slack_action_requests(created_at DESC)",
        "CREATE UNIQUE INDEX IF NOT EXISTS slack_action_requests_source_idx ON ops_agent.slack_action_requests(channel_id, source_message_ts, action)",
        "CREATE INDEX IF NOT EXISTS cloud_operation_audit_time_idx ON ops_agent.cloud_operation_audit(occurred_at DESC)",
        "CREATE INDEX IF NOT EXISTS cloud_operation_audit_request_idx ON ops_agent.cloud_operation_audit(request_id)",
        "CREATE INDEX IF NOT EXISTS app_user_audit_time_idx ON ops_agent.app_user_audit(occurred_at DESC)",
        "CREATE INDEX IF NOT EXISTS connector_credentials_org_idx ON ops_agent.connector_credentials(organization_id,provider)",
        "CREATE INDEX IF NOT EXISTS vmware_hosts_seen_idx ON ops_agent.vmware_hosts(last_seen_at DESC)",
        "CREATE INDEX IF NOT EXISTS vmware_vms_seen_idx ON ops_agent.vmware_virtual_machines(last_seen_at DESC)",
        "CREATE INDEX IF NOT EXISTS aws_ec2_inventory_seen_idx ON ops_agent.aws_ec2_inventory(last_seen_at DESC)",
        "CREATE INDEX IF NOT EXISTS ai_usage_events_time_idx ON ops_agent.ai_usage_events(occurred_at DESC)",
        "CREATE INDEX IF NOT EXISTS chat_sessions_user_idx ON ops_agent.chat_sessions(requester,updated_at DESC)",
        "CREATE INDEX IF NOT EXISTS chat_messages_session_idx ON ops_agent.chat_messages(session_id,id)",
    ]
    with connect() as connection:
        with connection.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)
        connection.commit()

"""Tenant-scoped integration catalog, connector registrations and gateway enrollment."""

import hashlib
import json
import secrets
import uuid

from psycopg.rows import dict_row

import database


CATALOG = [
    {"id": "aws", "name": "Amazon Web Services", "category": "Cloud", "connection_type": "api", "auth_type": "Cross-account IAM role", "maturity": "live", "description": "EC2 inventory and guarded AWS operations."},
    {"id": "azure", "name": "Microsoft Azure", "category": "Cloud", "connection_type": "api", "auth_type": "OAuth / workload identity", "maturity": "foundation", "description": "Azure resource discovery and governed operations."},
    {"id": "gcp", "name": "Google Cloud", "category": "Cloud", "connection_type": "api", "auth_type": "Workload identity", "maturity": "roadmap", "description": "Compute Engine and governed Google Cloud operations."},
    {"id": "oracle", "name": "Oracle Cloud", "category": "Cloud", "connection_type": "api", "auth_type": "OCI workload identity", "maturity": "roadmap", "description": "OCI compute, storage and network operations."},
    {"id": "ibmcloud", "name": "IBM Cloud", "category": "Cloud", "connection_type": "api", "auth_type": "Trusted profile", "maturity": "roadmap", "description": "Virtual server and infrastructure operations."},
    {"id": "alibaba", "name": "Alibaba Cloud", "category": "Cloud", "connection_type": "api", "auth_type": "RAM role", "maturity": "roadmap", "description": "ECS inventory and controlled cloud operations."},
    {"id": "datadog", "name": "Datadog", "category": "Observability", "connection_type": "api", "auth_type": "OAuth / scoped API application", "maturity": "roadmap", "description": "Monitor events, acknowledgement and investigation context."},
    {"id": "solarwinds", "name": "SolarWinds", "category": "Observability", "connection_type": "api_or_gateway", "auth_type": "Secured webhook", "maturity": "foundation", "description": "Infrastructure alerts and operational context."},
    {"id": "nagios", "name": "Nagios", "category": "Observability", "connection_type": "api_or_gateway", "auth_type": "Secured webhook", "maturity": "foundation", "description": "Host and service alert notifications."},
    {"id": "grafana", "name": "Grafana", "category": "Observability", "connection_type": "api_or_gateway", "auth_type": "Webhook / service account", "maturity": "demo", "description": "Alert webhook intake and operational response."},
    {"id": "slack", "name": "Slack", "category": "Collaboration", "connection_type": "api", "auth_type": "OAuth application", "maturity": "live", "description": "Requests, approvals and verified results."},
    {"id": "gmail", "name": "Gmail / Outlook", "category": "Communication", "connection_type": "api", "auth_type": "App password / service account", "maturity": "live", "description": "Email requests, approvals and completion notifications."},
    {"id": "sccm", "name": "Microsoft SCCM / WSUS", "category": "Endpoint management", "connection_type": "gateway", "auth_type": "Customer gateway", "maturity": "inventory_live", "description": "Private inventory and governed patch orchestration."},
    {"id": "vmware", "name": "VMware vCenter", "category": "Infrastructure", "connection_type": "gateway", "auth_type": "Customer gateway", "maturity": "foundation", "description": "vCenter inventory and controlled VM operations."},
    {"id": "nutanix", "name": "Nutanix AHV", "category": "Infrastructure", "connection_type": "gateway", "auth_type": "Customer gateway", "maturity": "roadmap", "description": "Cluster, VM and storage operations."},
    {"id": "openstack", "name": "OpenStack", "category": "Infrastructure", "connection_type": "gateway", "auth_type": "Customer gateway", "maturity": "roadmap", "description": "Compute, network and volume operations."},
    {"id": "hyperv", "name": "Microsoft Hyper-V", "category": "Infrastructure", "connection_type": "gateway", "auth_type": "Customer gateway", "maturity": "roadmap", "description": "Host, cluster and VM lifecycle operations."},
    {"id": "kubernetes", "name": "Kubernetes / OpenShift", "category": "Infrastructure", "connection_type": "gateway", "auth_type": "Customer gateway", "maturity": "roadmap", "description": "Cluster and workload operations."},
    {"id": "windows", "name": "Windows Server", "category": "Server operations", "connection_type": "gateway", "auth_type": "Customer gateway", "maturity": "live", "description": "Allowlisted PowerShell and SSM operations."},
    {"id": "linux", "name": "Linux", "category": "Server operations", "connection_type": "gateway", "auth_type": "Customer gateway", "maturity": "foundation", "description": "Allowlisted SSH and local agent runbooks."},
    {"id": "hardware", "name": "Datacenter hardware", "category": "Datacenter", "connection_type": "gateway", "auth_type": "Customer gateway", "maturity": "roadmap", "description": "Cisco UCS, Dell and HPE operations."},
    {"id": "network", "name": "Network and security", "category": "Datacenter", "connection_type": "gateway", "auth_type": "Customer gateway", "maturity": "roadmap", "description": "Cisco, Fortinet, Palo Alto and F5 operations."},
    {"id": "storage", "name": "Enterprise storage", "category": "Datacenter", "connection_type": "gateway", "auth_type": "Customer gateway", "maturity": "roadmap", "description": "NetApp, Pure Storage and Dell storage operations."},
]


def catalog():
    return CATALOG


def list_connections(organization_id: str):
    with database.connect(row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute("""SELECT * FROM (SELECT DISTINCT ON (provider)
                connection_id, provider, display_name, connection_type, status,
                endpoint, credential_reference, configuration, last_tested_at, last_error, created_at, updated_at
                FROM ops_agent.integration_connections WHERE organization_id=%s
                ORDER BY provider,
                    CASE WHEN status IN ('configured','connected','active') THEN 0 ELSE 1 END,
                    created_at DESC) latest ORDER BY created_at DESC""", (organization_id,))
            return cursor.fetchall()


def create_connection(organization_id: str, actor: str, provider: str, display_name: str,
                      connection_type: str, endpoint: str | None, credential_reference: str | None,
                      configuration: dict):
    if provider not in {item["id"] for item in CATALOG}:
        raise ValueError("Unknown integration provider")
    if connection_type not in {"api", "gateway"}:
        raise ValueError("Connection type must be api or gateway")
    connection_id = f"con_{uuid.uuid4().hex}"
    with database.connect(row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute("""INSERT INTO ops_agent.integration_connections
                (connection_id, organization_id, provider, display_name, connection_type, status,
                 endpoint, credential_reference, configuration, created_by)
                VALUES (%s,%s,%s,%s,%s,'configured',%s,%s,%s::jsonb,%s) RETURNING *""",
                (connection_id, organization_id, provider, display_name, connection_type,
                 endpoint, credential_reference, json.dumps(configuration), actor))
            record = cursor.fetchone()
        connection.commit()
    return record


def create_gateway(organization_id: str, actor: str, name: str, platform: str):
    gateway_id = f"gw_{uuid.uuid4().hex}"
    token = secrets.token_urlsafe(36)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with database.connect(row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute("""INSERT INTO ops_agent.customer_gateways
                (gateway_id, organization_id, name, platform, status, enrollment_token_hash, created_by)
                VALUES (%s,%s,%s,%s,'pending',%s,%s) RETURNING gateway_id, organization_id, name, platform, status, created_at""",
                (gateway_id, organization_id, name, platform, token_hash, actor))
            record = dict(cursor.fetchone())
        connection.commit()
    record["enrollment_token"] = token
    return record


def list_gateways(organization_id: str):
    with database.connect(row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute("""SELECT gateway_id, name, platform, status, version, capabilities,
                last_heartbeat_at, created_at FROM ops_agent.customer_gateways
                WHERE organization_id=%s ORDER BY created_at DESC""", (organization_id,))
            return cursor.fetchall()

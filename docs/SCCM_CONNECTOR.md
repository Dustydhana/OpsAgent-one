# OpsAgent One SCCM connector

## Purpose

The connector provides live Microsoft Configuration Manager inventory to OpsAgent One without placing SCCM credentials or arbitrary PowerShell in the browser. The FastAPI control plane sends a fixed SSM Command document to the SCCM site server and records the request and result in PostgreSQL.

## Current capabilities

- Site and SMS Provider discovery
- Managed-device inventory and client activity
- Device collections and membership counts
- Deployments and high-level result counts
- Software-update groups
- Search, filtering, sorting, pagination and CSV export in React
- Manual synchronization with a short server-side cache
- Connector audit history
- Persistent monthly patch cycles with 11 governed stages
- KB, Software Update Group and deployment-package planning
- Test, pilot and production collection selection
- ServiceNow/Jira change references and approval state
- Stakeholder schedule, application-validation and completion email notifications
- Stage evidence and operator/approver history

## Patch pipeline

1. Microsoft release intake
2. Build update baseline
3. Lab test
4. Change creation
5. Stakeholder schedule notification
6. Human approval gate
7. One-day production preflight
8. Phased deployment
9. Live compliance monitoring
10. Application-team validation
11. Close and report

Planning, approval, notification, evidence and compliance orchestration are implemented in OpsAgent. SCCM mutation remains isolated behind separately published and allowlisted SSM documents. Do not treat creation of a patch-cycle record as permission to deploy software updates.

## Architecture

`React -> FastAPI -> AWS Systems Manager -> OPSAGENT-SCCM01 -> ConfigurationManager PowerShell -> structured JSON -> FastAPI -> React`

## Prerequisites

1. `OPSAGENT-SCCM01` is online in Systems Manager Fleet Manager.
2. Its EC2 role contains `AmazonSSMManagedInstanceCore`.
3. The instance has the tag `OpsAgentManaged=true`.
4. The Configuration Manager console and PowerShell module are installed.
5. The AWS runtime identity can use `ssm:SendCommand` for `OpsAgent-*` documents and tagged instances.
6. The SSM document `OpsAgent-sccm_inventory` is deployed in `us-east-1`.

## Deploy the document

From `server-downtime-agent`:

```powershell
aws ssm create-document `
  --name "OpsAgent-sccm_inventory" `
  --document-type "Command" `
  --document-format "JSON" `
  --content "file://connectors/aws/ssm/sccm-inventory.json" `
  --region us-east-1 `
  --profile opsagent
```

## Configuration

```dotenv
SCCM_MODE=ssm
SCCM_INSTANCE_ID=i-0da0c6e4524cbd334
SCCM_REGION=us-east-1
SCCM_INVENTORY_DOCUMENT=OpsAgent-sccm_inventory
SCCM_COMMAND_TIMEOUT_SECONDS=300
SCCM_CACHE_SECONDS=60
```

Restart the FastAPI process after changing environment values.

## API

- `GET /api/v1/sccm/status`
- `GET /api/v1/sccm/inventory`
- `GET /api/v1/sccm/inventory?refresh=true`
- `GET /api/v1/sccm/audit`
- `GET|POST /api/v1/sccm/patch-cycles`
- `GET /api/v1/sccm/patch-cycles/{cycle_id}`
- `POST /api/v1/sccm/patch-cycles/{cycle_id}/advance`
- `POST /api/v1/sccm/patch-cycles/{cycle_id}/approve`
- `GET /api/v1/sccm/patch-cycles/{cycle_id}/compliance`

## Security model

- Only a fixed, administrator-published SSM document executes.
- The target EC2 instance must carry the management tag.
- Inventory commands are read-only.
- Browser input cannot supply PowerShell.
- Every sync receives an OpsAgent request ID and SSM command ID.
- Future deployment or client-control documents require separate allowlisting, human approval and post-action verification.

## Troubleshooting

- `InvalidDocument`: deploy `OpsAgent-sccm_inventory` in the configured region.
- Target not online: verify Fleet Manager, the instance role, SSM Agent and DNS/HTTPS connectivity.
- Module not installed: install the Configuration Manager console on the SCCM connector server.
- No CMSite drive: open the Configuration Manager console once and verify the SMS Provider/site configuration.
- Access denied: verify document and tagged-instance `ssm:SendCommand` permissions.

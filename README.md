# Server Downtime Automation Agent

An AI agent that watches a Slack channel for server-alert messages, SSHes into
the affected AWS EC2 (Ubuntu) server, diagnoses the root cause with a set of
read-only commands, lets an OpenAI agent decide on and execute a safe
remediation, and posts a full incident report back to Slack.

Built for the HCLTech-OpenAI Agentic AI Hackathon (Track 2 - Enterprise Operations).

## How it works

```
Slack message in #ops-alerts
        │  (contains a keyword like "down", "alert", "error"...)
        ▼
main.py orchestrator
        │
        ▼
ssh_handler.py  ──connects via Paramiko──▶  EC2 Ubuntu server
        │
        ▼
diagnostics.py  runs: df -h, free -m, top -bn1, ps aux (mem/cpu),
                 systemctl list-units --state=failed, tail syslog
        │
        ▼
agent.py  sends diagnostics to OpenAI (gpt-4o-mini by default).
          The model reasons about root cause and may call tools:
            - restart_service
            - restart_all_failed_services
            - clear_disk_space
            - restart_heavy_process
            - no_action_needed
          Each tool call runs the matching function in remediation.py
          over the live SSH session, and the result is fed back to the
          model so it can decide on next steps (multi-turn loop).
        │
        ▼
diagnostics.py  runs again to capture post-fix server status
        │
        ▼
report.py + slack_handler.py  post a formatted incident report back
                               to the Slack channel
```

**Safety design note:** the LLM never generates raw shell commands to run.
It can only call a fixed, human-reviewed set of Python functions
(`remediation.py`), each of which validates its own arguments before
touching the server. This keeps the agent's blast radius bounded and
auditable, which matters a lot more than it sounds for a bot with SSH
access to production infrastructure.

## Project structure

```
server-downtime-agent/
├── main.py              # Entry point, starts Slack bot listener, orchestrates pipeline
├── agent.py             # OpenAI tool-calling reasoning loop
├── ssh_handler.py        # Paramiko SSH connection and command execution
├── diagnostics.py        # Disk/memory/CPU/log/failed-service check functions
├── remediation.py        # Auto-fix functions (restart service, clear disk, kill process)
├── slack_handler.py      # Slack message listening (Socket Mode) and posting
├── report.py             # Incident report / Slack Block Kit formatter
├── chart_generator.py    # Disk usage chart rendering for Slack and Streamlit
├── config.py              # All credentials and settings (reads from .env)
├── requirements.txt
├── .env.example
└── README.md
```

## New features

- **Free SCCM workflow simulation**: guarded patch deployments can be exercised
  without an SCCM server using `SCCM_MODE=simulation`. The simulator validates
  Test/Infra/Prod batches, collection allowlists, deployment timing, explicit
  approval, compliance states, and reboot suppression. It never installs a patch.

- **Disk space visualization**: when disk utilization exceeds 80%, OpsAgent scans
  the largest folders, generates a bar chart, uploads it to Slack, and shows the
  same view in Streamlit.
- **Patch management**: every investigation now includes recent installed patches,
  pending updates, and a patch-health recommendation in both Slack and Streamlit.
- **Server inventory retrieval**: PostgreSQL stores server name, IP,
  platform (AWS/Azure/on-prem/VMware), OS, application owner, monitoring service,
  important services, connection metadata, and routing context. Alerts use exact
  IP/hostname retrieval first, then a unique ranked text match, and inject only the
  matched server record into the investigation context.
- **Guarded AWS operations**: AWS inventory targets expose EC2 discovery and approved
  start, stop, reboot, instance resize (CPU/RAM), EBS extension, secondary-NIC detach,
  snapshot management, guarded EBS-volume deletion, and termination actions in Streamlit.
  Mutations require an exact approval phrase, an `AWS_ALLOWED_ACTIONS` entry, and are
  written to relational PostgreSQL audit and operational-log tables. `AWS_DRY_RUN=true`
  is the default so the management demo validates IAM authorization without changing EC2.

### Configure AWS operations

Use an EC2 instance role, workload identity, or a local AWS profile rather than storing
access keys in `.env`. Add `aws_instance_id` and `aws_region` to each AWS inventory record.
Start with `AWS_DRY_RUN=true`; after validation, set it to `false` only in an approved
environment. Stopping, resizing, NIC changes, and termination may cause downtime.

The EC2 role needs read-only `ec2:Describe*` permissions plus only the mutation permissions
you enable. EBS enlargement changes the cloud volume only; the guest filesystem must still
be expanded through a separately reviewed OS-specific action.

`delete_volume` is intentionally disabled by default. Before enabling it, grant only
`ec2:DeleteVolume` on the intended volume resources and test with a disposable volume.
OpsAgent requires an exact `vol-...` ID, `available` state, no attachments, explicit
approval, and the tag `OpsAgentDeletable=true`. Take a recovery snapshot first; EBS volume
deletion permanently removes the volume data unless an AWS Recycle Bin rule applies.

### Configure Streamlit login and roles

All Streamlit pages require a PostgreSQL-backed application account. Create the first
Admin interactively so no default or plain-text password is committed:

```powershell
python create_app_user.py
```

Passwords are salted and hashed with scrypt. Five failed attempts lock an account for
15 minutes. Admins can create users, reset passwords, assign roles, and disable access
from the User Management page. The last enabled Admin cannot be disabled or downgraded.

To recover a forgotten application password from the trusted application host, run:

```powershell
python reset_app_password.py
```

Optional self-service sign-up is enabled with `APP_SIGNUP_ENABLED=true`. New sign-ups
always receive the Viewer role and cannot promote themselves. The first application
account must still be created as an Admin from the terminal. Keep sign-up disabled on
an internet-facing deployment unless compensating registration controls are added.

- **Admin**: full dashboard access, user management, and destructive cloud actions.
- **Operator**: investigations and non-destructive allowlisted cloud actions.
- **Viewer**: read-only dashboards, inventory, audits, and logs.

Slack and Gmail maintain their separate configured requester and approver controls; a
Streamlit role does not replace those channel-specific approval rules.

### Configure the server inventory

Add records to the PostgreSQL `ops_agent.server_inventory` table and set `enabled` to
`true`. Keep credentials outside the inventory; production deployments should use
a secrets/PAM integration. The application has no local inventory fallback.

Exact IP/hostname lookup is used for alert execution because semantic similarity is
not safe enough to select a production target. The dashboard search provides a
RAG-style ranked discovery experience across application, team, OS, platform, tags,
and services. Inventory-defined important services are checked on every diagnostic
run and included in incident health classification.

For AWS records, store `public_ip_address` and `private_ip_address` as metadata and
set `ip_address` to the address SSH should actually use: public/Elastic IP when
OpsAgent runs outside the VPC, or private IP when it runs inside the same VPC or a
connected network. AWS API actions use `aws_instance_id`, so IP changes do not
affect control-plane operations.

## Prerequisites

- Python 3.11+
- An AWS EC2 instance running Ubuntu 22.04, reachable over SSH
- A Slack workspace where you can install an app
- An OpenAI API key

## 1. Set up the EC2 target server

1. Launch an Ubuntu 22.04 EC2 instance and download its key pair (e.g. `opsagent-key.pem`).
2. In the instance's Security Group, allow inbound SSH (port 22) from the IP address
   that will run this agent.
3. The bot connects as the `ubuntu` user and needs `sudo` for some remediation actions
   (restarting services, clearing logs, killing processes). For a hackathon demo, add a
   sudoers file so those specific commands don't prompt for a password:

   ```bash
   sudo visudo -f /etc/sudoers.d/opsagent
   ```

   Add:

   ```
   ubuntu ALL=(ALL) NOPASSWD: /bin/systemctl restart *, /bin/systemctl is-active *, \
     /usr/bin/systemctl list-units *, /usr/bin/journalctl --vacuum-time=*, \
     /usr/bin/find /tmp -type f -atime +2 -delete, /usr/bin/find /var/log -name *.gz -delete, \
     /usr/bin/find /var/log -name *.log.* -mtime +7 -delete, /usr/bin/apt-get clean -y, \
     /bin/kill -9 *, /usr/bin/pkill -9 -f *
   ```

   > This is intentionally permissive for demo purposes. For anything beyond a hackathon,
   > scope each rule down further (e.g. restrict `kill -9` to specific known PIDs/users)
   > and consider a dedicated low-privilege service account instead of `ubuntu`.

### Install the demo monitoring service

Copy `setup_demo_service.sh` to the Linux target and run:

```bash
chmod +x setup_demo_service.sh
sudo ./setup_demo_service.sh
sudo systemctl enable ops-telemetry
```

For the false-alert demo, stop it with `sudo systemctl stop ops-telemetry` before
posting the alert. OpsAgent will detect and restart it automatically.

If a real AWS host does not have the configured monitoring service installed,
OpsAgent reports that as a monitoring configuration issue instead of treating
the server as down.

## Web application

Start the FastAPI backend from the project root:

```bash
uvicorn backend.main:app --reload --port 8000
```

Start the React application in a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. FastAPI now starts Slack, Gmail, and inventory
background connectors itself; do not run `python main.py` in a third terminal.
Set `OPSAGENT_CONNECTORS_IN_API=false` only when connector workers are hosted in
a separate production process.

### Configure VMware operations

The VMware panel works with either a standalone ESXi host or vCenter. Start
with a disposable lab endpoint and keep dry-run enabled:

```dotenv
VMWARE_ENDPOINT=192.168.51.130
VMWARE_PORT=443
VMWARE_USERNAME=root
VMWARE_PASSWORD=replace-with-secret
VMWARE_VERIFY_SSL=false
VMWARE_DRY_RUN=true
VMWARE_ALLOWED_ACTIONS=power_on_vm,power_off_vm,reboot_guest,create_snapshot,remove_snapshot,resize_vm,extend_disk,enter_maintenance,exit_maintenance,reboot_host,shutdown_host,create_vm,patch_host
```

Open **Cloud Operations → VMware / On-premises**. Read-only discovery loads once
per endpoint and shows product/build details, ESXi health,
datastore capacity, networks, and VMs. Change workflows require an authenticated
Operator or Admin, an allowlisted action, and the exact approval phrase shown by
the dashboard. Every attempt is written to `ops_agent.cloud_operation_audit`.
Each successful refresh also replaces the endpoint's relational PostgreSQL
inventory snapshot in `vmware_endpoints`, `vmware_hosts`, `vmware_datastores`,
`vmware_networks`, and `vmware_virtual_machines` under the `ops_agent` schema.

`VMWARE_DRY_RUN=true` validates and audits the requested workflow without making
a VMware change. With dry-run disabled, VM power, guest reboot, snapshot,
powered-off VM resize/disk extension, maintenance-mode, and non-forced host
power operations use the vSphere API. The endpoint license must permit API
write access. `create_vm` and `patch_host` remain plan-only even in live mode:
production versions must define approved images or patch baselines, networks,
storage policy, evacuation, compatibility, verification, and rollback rules.

For production, connect to vCenter with a dedicated least-privilege service
account, a trusted TLS certificate, `VMWARE_VERIFY_SSL=true`, and a narrowly
scoped action allowlist. A virtual-disk extension changes only the VMware device;
expanding the guest partition/filesystem is a separate reviewed operation.

## Architecture

```
Slack / Email / Streamlit
          |
          +-- investigation/ --> shared remote diagnostics and remediation
          |
          +-- providers/ -----> AWS | Azure | VMware | On-premises
                                  |
                                  +-- guarded provider API operations
```

`providers/` is the only provider-facing boundary for new channel and UI code.
`investigation/` exposes the common orchestration used by Slack and Streamlit.
The root `aws_operations.py` module remains temporarily available for backward
compatibility with existing deployments and tests.

All persistent application state is stored in PostgreSQL under the
`ops_agent` schema: inventory, alert events, utilization history, component
health, email approvals, and cloud-operation audits. `DATABASE_URL` is required;
the application deliberately has no JSON/JSONL file fallback and uses no
JSON/JSONB database columns.

The Streamlit dashboard also includes a target-aware VM troubleshooting chat.
Choose any enabled PostgreSQL inventory server (or enter an exact manual
host), then ask about health, CPU, memory, disk, patches, services, logs,
reboots, or a full overview. OpsAgent collects fresh read-only evidence when
the target or diagnostic topic changes and reuses it for follow-up questions.
Start/stop/reboot and other cloud mutations are intentionally refused in chat
and remain available only through the audited Slack/Gmail approval workflows.

For new environments, use `DEFAULT_TARGET_HOST` instead of the legacy
AWS-specific `EC2_HOST` name. Existing `.env` files continue to work.

## 2. Create the Slack app

1. Go to <https://api.slack.com/apps> → **Create New App** → From scratch.
2. **Socket Mode**: enable it (Settings → Socket Mode). Generate an app-level token with
   the `connections:write` scope — this is your `SLACK_APP_TOKEN` (`xapp-...`).
3. **OAuth & Permissions** → add these Bot Token Scopes:
   - `chat:write`
   - `app_mentions:read`
   - `files:write`
   - `channels:read`
   - `channels:history`
   - `groups:read` and `groups:history` (only if `#ops-alerts` will be a private channel)
4. **Event Subscriptions**: enable events, and subscribe to bot events `message.channels`
   and `app_mention` (add `message.groups` too if using a private channel).
5. Install the app to your workspace. Copy the **Bot User OAuth Token** — this is your
   `SLACK_BOT_TOKEN` (`xoxb-...`).
6. Create the `#ops-alerts` channel (if it doesn't exist) and **invite the bot** to it
   (`/invite @YourBotName`).

## 3. Get an OpenAI API key

Create one at <https://platform.openai.com/api-keys>.

## 4. Install and configure

```bash
cd server-downtime-agent
python -m venv .venv
.venv\Scripts\activate      # Windows
# source .venv/bin/activate # macOS/Linux

pip install -r requirements.txt

copy .env.example .env      # Windows
# cp .env.example .env      # macOS/Linux
```

Edit `.env` and fill in:

```
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...
SLACK_CHANNEL=#ops-alerts
APPLICATION_OWNER_EMAIL=app-owner@example.com
SMTP_HOST=smtp.office365.com
SMTP_PORT=587
SMTP_USERNAME=ops-agent@example.com
SMTP_PASSWORD=<smtp-password-or-app-password>
SMTP_FROM_EMAIL=ops-agent@example.com
SMTP_USE_TLS=true
OPENAI_API_KEY=...
DEFAULT_TARGET_HOST=<reachable-ip-or-dns-of-your-default-server>
# EC2_HOST remains supported as a legacy fallback
EC2_USERNAME=ubuntu
EC2_KEY_PATH=./opsagent-key.pem
WINDOWS_EC2_HOST=<windows-public-ip-or-dns>
WINDOWS_EC2_USERNAME=Administrator
WINDOWS_EC2_KEY_PATH=./opsagent-key.pem
WINDOWS_EC2_SSH_PORT=22
MONITORING_SERVICE_NAME=Alloy
MONITORING_SERVICE_INSTALL_HINT=Install and enable Grafana/your monitoring agent on this host.
```

Place your `opsagent-key.pem` file in the project directory (or point `EC2_KEY_PATH` at
wherever it lives).

Email escalation is optional. When `APPLICATION_OWNER_EMAIL` and the SMTP settings are
configured, every genuine incident is emailed to the application owner. The email includes
the alert, utilization, diagnosis, remediation actions, and largest disk-consuming folders.
Leave `APPLICATION_OWNER_EMAIL` blank to keep email disabled.

### Inbound email requests with approval

Set `INBOUND_EMAIL_ENABLED=true` and configure the IMAP mailbox, exact requester
allowlist, and exact approver allowlist. A requester can send:

```text
AWS REQUEST stop_instance i-0b803014af102ad61
```

OpsAgent acknowledges the request and emails a short-lived `OPS-...` request ID to
the approvers. No AWS mutation occurs until an allowlisted approver replies with
`APPROVE OPS-XXXXXXXX`. The action must also be present in `AWS_ALLOWED_ACTIONS`,
pass IAM authorization, and is governed by `AWS_DRY_RUN`. Results are emailed to
the requester and approver and written to the existing AWS audit log.

### Slack AWS requests with approval

Configure one or more approvers using Slack user IDs where possible:

```text
SLACK_APPROVERS=U0123456789,U9876543210
SLACK_APPROVAL_EXPIRY_MINUTES=15
SLACK_AWS_VERIFY_SECONDS=120
SLACK_ALLOW_SELF_APPROVAL=false
```

The guarded Slack flow is:

```text
@Ops agent start AWS-MS-OPSTESTVM
APPROVE SLK-XXXXXXXX
```

The first message only creates a PostgreSQL request and acknowledgement. An
authorized approver must send the exact second command before expiry. OpsAgent
then performs the allowlisted AWS operation asynchronously, verifies the
before/after EC2 state, replies in the original Slack thread, and retains the
requester, approver, target, result, and error fields in PostgreSQL. Keep
`SLACK_ALLOW_SELF_APPROVAL=false` in company environments so the requester and
approver must be different people.

Guarded EBS snapshot examples use the same approval flow:

```text
@Ops agent take snapshot AWS-MS-OPSTESTVM
@Ops agent delete snapshot snap-0123456789abcdef0 region=us-east-1
```

For Gmail, use `AWS REQUEST create_snapshot <instance-id>` with an optional
`volume_id=vol-...`, or `AWS REQUEST delete_snapshot <snapshot-id>`. Snapshot
deletion always requires the exact snapshot ID and a separate approval.

The optional Windows target uses its own username while allowing the same PEM key to be
reused. Windows OpenSSH Server must be installed and running, port 22 must be allowed by
the EC2 security group and Windows Firewall, and the matching public key must be authorized
for `WINDOWS_EC2_USERNAME`.

## 5. Run it

```bash
python main.py
```

You should see:

```
Server Downtime Automation Agent starting...
Target server: ubuntu@<your-ec2-ip>
Alert keywords: ['down', 'alert', 'server', ...]
[slack_handler] Watching channel '#ops-alerts' (id=C0XXXXXXX)
```

## 6. Try it

Post a message like this in `#ops-alerts`:

```
🚨 server alert: prod-01 disk usage critical, app not responding
```

The bot will reply immediately with an acknowledgement, then a few seconds to a couple of
minutes later post a full incident report with the diagnosis, every remediation action it
took, and the current server status.

If disk usage is above 80%, the bot also uploads a folder-size chart to Slack.
If critical or important patches are pending, the incident report includes a
patch-management summary and recommendation.

## Troubleshooting

## Governed Windows and Linux execution with AWS Systems Manager

The enterprise Windows/Linux catalogs execute through AWS Systems Manager,
not through browser-provided PowerShell or shell text. For each enabled action:

1. Create an SSM Command document named `OpsAgent-<operation_slug>` (for example,
   `OpsAgent-create_domain_user`) and validate every accepted parameter.
2. Give the control-plane role scoped `ssm:SendCommand`,
   `ssm:GetCommandInvocation`, and `ssm:DescribeInstanceInformation` permissions.
3. Ensure every target is online in Systems Manager. Domain, DNS, and DHCP documents
   must use a constrained service identity or retrieve credentials from an approved
   secret store; never send passwords through browser parameters.
4. Add exact operation slugs to `SSM_ALLOWED_ACTIONS`. Keep
   `SSM_OPERATIONS_DRY_RUN=true` during validation, then set it to `false` only where
   live execution is authorized.

The API requires Operator/Admin access and an exact confirmation phrase, resolves only
the fixed document namespace, waits for the result, returns bounded output, and records
the request and outcome in the operational audit log.

- **"Missing required environment variable(s)"** — `.env` wasn't filled in or wasn't found;
  make sure you're running `python main.py` from inside `server-downtime-agent/`.
- **SSH authentication failed** — check `EC2_USERNAME` (should be `ubuntu` for stock Ubuntu
  AMIs) and that `EC2_KEY_PATH` points to the matching `.pem` file for that instance.
- **Bot doesn't respond to messages** — confirm the bot was invited to the channel and that
  Socket Mode + the `message.channels` and `app_mention` event subscriptions are enabled.
- **Remediation actions report "Permission denied"** — the sudoers rules from step 1 aren't
  in place, or don't match the exact commands being run.

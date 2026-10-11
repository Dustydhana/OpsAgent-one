# OpsAgent AWS connector

This package connects a customer AWS account to OpsAgent without storing a customer access key. It uses AWS STS and a customer-managed, least-privilege cross-account IAM role.

## Security model

- Inventory access is read-only.
- EC2 and EBS APIs provide network, instance and attached-volume metadata. Systems Manager provides exact managed-node OS version and hostname metadata when SSM Agent is configured.
- Start, stop and reboot are disabled by default.
- Optional operations apply only to EC2 instances tagged `OpsAgentManaged=true`.
- The trust policy requires a unique external ID to prevent confused-deputy access.
- The AI model never receives AWS credentials.
- OpsAgent RBAC, confirmation, allowlists and audit still apply after AWS authorizes a call.

## Prerequisites

1. AWS CLI v2 and permission to deploy IAM roles in the customer account.
2. The ARN of the IAM role used by the OpsAgent control plane. For a local lab this may be an IAM user ARN, but an IAM role is recommended.
3. Python dependencies from the OpsAgent `requirements.txt`.

## 1. Generate a customer external ID

PowerShell:

```powershell
$externalId = ([guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N"))
$externalId
```

Keep this value in the control-plane secret store. It is not an AWS access key.

## 2. Deploy the connector role in the customer AWS account

Run from this repository root after authenticating the AWS CLI to the customer account:

```powershell
aws cloudformation deploy `
  --region us-east-1 `
  --stack-name opsagent-connector `
  --template-file connectors/aws/cloudformation/opsagent-connector-role.yaml `
  --capabilities CAPABILITY_NAMED_IAM `
  --parameter-overrides `
    OpsAgentPrincipalArn="arn:aws:iam::CONTROL_PLANE_ACCOUNT_ID:role/OpsAgentControlPlaneRole" `
    ExternalId="$externalId" `
    EnableGuardedOperations="false" `
    EnableSsmOperations="false" `
    EnableProvisioning="false"
```

Obtain the created role ARN:

```powershell
aws cloudformation describe-stacks `
  --region us-east-1 `
  --stack-name opsagent-connector `
  --query "Stacks[0].Outputs[?OutputKey=='RoleArn'].OutputValue" `
  --output text
```

## 3. Authorize the control-plane identity

Attach `control-plane-assume-role-policy.json` to the OpsAgent control-plane IAM role after replacing `CUSTOMER_CONNECTOR_ROLE_ARN`. This grants only `sts:AssumeRole` to that customer connector.

## 4. Configure OpsAgent

Set these only on FastAPI or in its secret manager—not in React:

```dotenv
AWS_REGION=us-east-1
AWS_INVENTORY_REGIONS=us-east-1
AWS_ROLE_ARN=arn:aws:iam::CUSTOMER_ACCOUNT_ID:role/OpsAgentConnectorRole
AWS_EXTERNAL_ID=the-generated-external-id
AWS_ROLE_SESSION_NAME=opsagent-connector
AWS_INVENTORY_SYNC_ENABLED=true
AWS_INVENTORY_SYNC_INTERVAL_SECONDS=300
AWS_DRY_RUN=true
AWS_ALLOWED_ACTIONS=
```

Restart FastAPI after changing environment variables.

## 5. Test before synchronizing

From the activated OpsAgent virtual environment:

```powershell
python connectors/aws/scripts/test_connection.py
```

Or authenticate to OpsAgent and call:

```http
POST /api/v1/connections/aws/test
Authorization: Bearer <opsagent-session-token>
```

The response returns account, assumed principal, region and authentication method. It never returns credentials.

## 6. Enable guarded operations later

First tag only disposable approved resources:

```powershell
aws ec2 create-tags --resources i-0123456789abcdef0 --tags Key=OpsAgentManaged,Value=true
```

Redeploy the CloudFormation stack with `EnableGuardedOperations="true"`, then configure:

```dotenv
AWS_DRY_RUN=true
AWS_ALLOWED_ACTIONS=start_instance,stop_instance,reboot_instance
```

Validate dry-run behavior and audit records before setting `AWS_DRY_RUN=false`.

## 7. Enable approval-gated EC2 provisioning

Update the stack with `EnableProvisioning="true"`. This creates the dedicated
`OpsAgentManagedInstanceRole` and `OpsAgentManagedInstanceProfile` and permits
only allowlisted instance sizes when the request includes
`OpsAgentManaged=true` and `ManagedBy=OpsAgent` tags.

Keep dry-run enabled first:

```dotenv
AWS_DRY_RUN=true
AWS_ALLOWED_ACTIONS=start_instance,stop_instance,reboot_instance,provision_instance
```

In OpsAgent Chat, open **New EC2 request**, validate the resolved AMI, VPC,
subnet and security-group IDs, and enter the displayed approval phrase. A dry
run verifies AWS authorization without creating a resource. Set
`AWS_DRY_RUN=false` only after this succeeds and the customer approves live
provisioning.

## Production requirements

- Use one connector role and unique external ID per customer account.
- Store external IDs and role mappings in a secrets manager or encrypted tenant store.
- Do not reuse a developer IAM user across customers.
- Send CloudTrail management events to the customer's central audit account.
- Apply an SCP or permissions boundary when the customer requires another control layer.
- Rotate or revoke access by updating the role trust policy; no access keys need rotation.

The current application configuration supports one active environment-based AWS connector. Multi-account, organization-scoped connector records and encrypted secret storage are the next control-plane milestone.

# Windows domain join runbook

OpsAgent joins an SSM-managed Windows server to Active Directory without sending a domain password through the browser. The UI accepts only the identifier of an AWS Secrets Manager secret.

## 1. Store the domain credential

In AWS Secrets Manager, create a secret named under this path:

```text
opsagent/domain-join/service-account
```

Use this JSON structure:

```json
{
  "username": "OPSAGENT\\svc-domainjoin",
  "password": "replace-with-the-account-password"
}
```

The domain account should have only the permission to join computers in the intended OU. Do not enter an IAM role ARN or the password in the OpsAgent form.

## 2. Update the connector stack

Update the existing `opsagent-connector` CloudFormation stack with the current `connectors/aws/cloudformation/opsagent-connector-role.yaml` template. This grants `OpsAgentManagedInstanceRole` read access only to `opsagent/domain-join/*` secrets.

If the secret uses a customer-managed KMS key, its key policy must also allow `OpsAgentManagedInstanceRole` to call `kms:Decrypt`.

## 3. Publish the SSM document

Run from the `server-downtime-agent` directory:

```powershell
aws ssm create-document `
  --name "OpsAgent-join_computer_to_domain" `
  --document-type "Command" `
  --document-format "JSON" `
  --content "file://connectors/aws/ssm/join-computer-to-domain.json" `
  --region us-east-1 `
  --profile opsagent
```

If the document already exists, publish a new version:

```powershell
aws ssm update-document `
  --name "OpsAgent-join_computer_to_domain" `
  --document-version '$LATEST' `
  --document-format "JSON" `
  --content "file://connectors/aws/ssm/join-computer-to-domain.json" `
  --region us-east-1 `
  --profile opsagent
```

## 4. Execute

In Windows operations, enter the AD DNS name, the Secrets Manager name `opsagent/domain-join/service-account`, an optional OU distinguished name, and whether the approved operation may restart the server. The target must resolve the domain DNS name and reach a domain controller.

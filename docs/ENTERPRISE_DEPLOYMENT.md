# A2Z OpsAgent enterprise deployment

## Operating model

Deploy the React, FastAPI and PostgreSQL control plane centrally. Install a customer agent inside every managed network. Agents initiate outbound TLS connections, retain provider credentials locally, enforce allowlists, execute approved work and return sanitized results.

## Customer onboarding

1. Create the organization and administrator.
2. Deploy PostgreSQL with encryption and backups.
3. Deploy FastAPI and React behind TLS.
4. Generate a one-time customer-agent registration token.
5. Install the agent as a Windows service, Linux systemd service or Kubernetes workload.
6. Approve the agent and assign its environment and policies.
7. Connect infrastructure with least-privilege identities.
8. Validate inventory and read-only diagnostics.
9. Select a managed model, private model or rules-only mode.
10. Enable mutations gradually with RBAC, approval, verification and audit.

## Model options

- OpenAI
- Azure OpenAI
- AWS Bedrock
- Ollama
- vLLM
- Rules-only mode

The model never receives infrastructure credentials and cannot bypass authorization, approval or the customer agent's local policy.

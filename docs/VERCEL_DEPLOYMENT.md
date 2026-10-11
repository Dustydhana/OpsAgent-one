# Vercel deployment

OpsAgent uses a split production architecture:

- **Vercel:** the compiled React/Vite frontend.
- **Persistent application host:** FastAPI and long-running Slack, Gmail, inventory, SSH, AWS and VMware workers.
- **Managed PostgreSQL:** a network-accessible PostgreSQL service with backups and TLS.

The FastAPI process must not be deployed as a Vercel serverless function. Its connector workers and infrastructure operations require persistent processes and network access that are outside the Vercel function lifecycle.

## 1. Deploy the API

Deploy this repository to a persistent Python host such as AWS ECS/EC2, Azure Container Apps, Render, Railway or Fly.io. Start the API with:

```text
uvicorn backend.main:app --host 0.0.0.0 --port $PORT
```

Use `/api/v1/health` as the liveness probe and `/api/v1/ready` as the readiness probe.

Required production settings include:

```text
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DATABASE?sslmode=require
OPSAGENT_API_SECRET=<long-random-secret>
OPSAGENT_FRONTEND_URL=https://YOUR-PROJECT.vercel.app
OPSAGENT_OAUTH_CALLBACK_BASE=https://YOUR-API-DOMAIN
OPSAGENT_CORS_ORIGINS=https://YOUR-PROJECT.vercel.app
OPSAGENT_COOKIE_SECURE=true
OPSAGENT_CONNECTORS_IN_API=true
```

For a web-only API replica, set `OPSAGENT_CONNECTORS_IN_API=false` and run connectors in one dedicated worker process to prevent duplicate Slack, Gmail and inventory consumers.

Register OAuth callback URLs using the API domain, for example:

```text
https://YOUR-API-DOMAIN/api/v1/auth/oauth/google/callback
```

## 2. Deploy the frontend to Vercel

Import the repository into Vercel and set the project root to `server-downtime-agent` if the repository contains a parent directory. `vercel.json` builds `frontend` and publishes `frontend/dist`.

Add this Vercel environment variable before building:

```text
VITE_API_URL=https://YOUR-API-DOMAIN
```

Do not append `/api/v1`; the frontend adds it automatically.

## 3. Verify production

1. `GET https://YOUR-API-DOMAIN/api/v1/health` returns `healthy`.
2. `GET https://YOUR-API-DOMAIN/api/v1/ready` returns `ready` and `database: connected`.
3. The Vercel login page lists configured identity providers.
4. Local and OAuth login redirect back to the Vercel URL.
5. Dashboard, connections, inventory and audit pages load without CORS errors.
6. Exactly one connector worker consumes Slack/Gmail events.

Never upload `.env`, database backups, private keys or the local `.venv` directory to Vercel.

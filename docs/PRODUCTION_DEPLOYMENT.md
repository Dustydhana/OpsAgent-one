# OpsAgent One production deployment

The production topology is intentionally split:

- Vercel serves the React frontend.
- A persistent container host runs the FastAPI API.
- Managed PostgreSQL stores all tenant data.

Do not deploy the FastAPI API as a Vercel function. Its connector workers, long-running operations and database lifecycle require a persistent service.

## 1. Create managed PostgreSQL

Create a PostgreSQL database with any managed provider. For a low-cost first environment, a free development database can be used; production requires backups, recovery guarantees and sufficient connection limits.

Copy its pooled connection string and ensure TLS is required:

```text
postgresql://USER:PASSWORD@HOST/DATABASE?sslmode=require
```

Keep this value only in the backend host as `DATABASE_URL`.

## 2. Deploy the backend

Import this repository into a container host using `render.yaml`, or build the included `Dockerfile` on another platform.

Set all values from `backend.env.example`. Generate the API secret locally:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

The container performs these steps on every release:

1. validates production security settings;
2. creates missing database objects;
3. runs idempotent tenant-isolation migrations;
4. starts one Uvicorn web process.

Verify:

```text
https://YOUR-API/api/v1/health
https://YOUR-API/api/v1/ready
```

The readiness endpoint must report `database: connected`.

## 3. Deploy the frontend to Vercel

Import the same repository. The root `vercel.json` already builds `frontend/`.

Set:

```text
VITE_API_URL=https://YOUR-API
```

Redeploy after changing any `VITE_` variable because Vite embeds it during the build.

## 4. Configure OAuth redirects

Set the backend values:

```text
OPSAGENT_FRONTEND_URL=https://YOUR-FRONTEND.vercel.app
OPSAGENT_OAUTH_CALLBACK_BASE=https://YOUR-API
OPSAGENT_CORS_ORIGINS=https://YOUR-FRONTEND.vercel.app
OPSAGENT_COOKIE_SECURE=true
```

Microsoft redirect URI:

```text
https://YOUR-API/api/v1/auth/oauth/microsoft/callback
```

Google redirect URI:

```text
https://YOUR-API/api/v1/auth/oauth/google/callback
```

## 5. Release checks

Run locally before every release:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
npm --prefix frontend ci
npm --prefix frontend run build
```

Keep `AWS_DRY_RUN`, `VMWARE_DRY_RUN` and `SSM_OPERATIONS_DRY_RUN` enabled until a controlled non-production acceptance test has passed. Run Slack, Gmail and scheduled inventory connectors as a separate worker service before enabling multiple web replicas.

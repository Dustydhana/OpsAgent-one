# A2Z OpsAgent enterprise preview

The existing Streamlit application remains operational. The enterprise preview runs beside it and uses the same Python services and PostgreSQL database.

## Backend

```powershell
cd server-downtime-agent
.\.venv\Scripts\pip.exe install -r requirements.txt
$env:OPSAGENT_API_SECRET="replace-with-a-long-random-production-secret"
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --port 8000
```

API documentation: `http://localhost:8000/api/docs`

## Frontend

Open another terminal:

```powershell
cd server-downtime-agent\frontend
npm.cmd install
npm.cmd run dev
```

Enterprise UI: `http://localhost:5173`

Sign in with the same PostgreSQL-backed account used by Streamlit.

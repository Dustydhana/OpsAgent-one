"""Relational PostgreSQL operational logging for live diagnostics."""

import threading
import database
import config

_READY = False
_LOCK = threading.Lock()


def _ready():
    global _READY
    if not _READY:
        with _LOCK:
            if not _READY:
                database.initialize()
                _READY = True


def write(component, level, event, details="", correlation_id="", organization_id=None):
    """Persist a sanitized operational event without interrupting the workflow."""
    try:
        _ready(); organization_id = str(organization_id or config.DEFAULT_ORGANIZATION_ID or "").strip()
        if not organization_id: raise ValueError("organization_id is required")
        with database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""INSERT INTO ops_agent.operational_logs
                    (organization_id,component,level,event,details,correlation_id) VALUES (%s,%s,%s,%s,%s,%s)""",
                    (organization_id,str(component), str(level).upper(), str(event), str(details or ""),
                     str(correlation_id or "") or None))
            connection.commit()
    except Exception as exc:
        print(f"[ops_log] Could not persist {component}/{event}: {type(exc).__name__}: {exc}")


def recent(*, component="all", level="all", limit=250, organization_id=None):
    _ready()
    organization_id = str(organization_id or config.DEFAULT_ORGANIZATION_ID or "").strip()
    if not organization_id: raise ValueError("organization_id is required")
    clauses, params = ["organization_id = %s"], [organization_id]
    if component != "all":
        clauses.append("component = %s")
        params.append(component)
    if level != "all":
        clauses.append("level = %s")
        params.append(level.upper())
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    params.append(max(1, min(int(limit), 2000)))
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(f"""SELECT occurred_at,component,level,event,details,correlation_id
                FROM ops_agent.operational_logs{where} ORDER BY occurred_at DESC LIMIT %s""", params)
            rows = cursor.fetchall()
    return [{"Time":r[0].astimezone().strftime("%Y-%m-%d %H:%M:%S"),"Component":r[1],
             "Level":r[2],"Event":r[3],"Details":r[4] or "","Correlation ID":r[5] or ""} for r in rows]


def components():
    _ready()
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT DISTINCT component FROM ops_agent.operational_logs ORDER BY component")
            return [row[0] for row in cursor.fetchall()]

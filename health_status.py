"""PostgreSQL-backed component heartbeat store for the dashboard."""

from datetime import datetime
import database


def _ensure_table(connection):
    with connection.cursor() as cursor:
        cursor.execute("""CREATE TABLE IF NOT EXISTS ops_agent.component_health (
            component TEXT PRIMARY KEY, status TEXT NOT NULL, details TEXT NOT NULL DEFAULT '',
            last_heartbeat TIMESTAMPTZ NOT NULL DEFAULT NOW())""")


def update(component, status, details=""):
    try:
        with database.connect() as connection:
            _ensure_table(connection)
            with connection.cursor() as cursor:
                cursor.execute("""INSERT INTO ops_agent.component_health (component, status, details)
                    VALUES (%s, %s, %s) ON CONFLICT (component) DO UPDATE SET
                    status=EXCLUDED.status, details=EXCLUDED.details, last_heartbeat=NOW()""",
                    (component, status, str(details or "")))
            connection.commit()
        return True
    except Exception as error:
        print(f"[health_status] Could not persist {component}: {type(error).__name__}: {error}")
        return False


def read():
    with database.connect() as connection:
        _ensure_table(connection)
        with connection.cursor() as cursor:
            cursor.execute("SELECT component, status, details, last_heartbeat FROM ops_agent.component_health")
            rows = cursor.fetchall()
        connection.commit()
    return {row[0]: {"status": row[1], "details": row[2], "last_heartbeat": row[3]} for row in rows}


def display_rows():
    data = read()
    names = ("slack", "grafana_polling", "queue_worker", "smtp", "ssh", "inbound_email", "database")
    rows = []
    for name in names:
        item = data.get(name, {})
        heartbeat = item.get("last_heartbeat")
        heartbeat = heartbeat.astimezone().strftime("%Y-%m-%d %H:%M:%S") if isinstance(heartbeat, datetime) else "Not recorded"
        rows.append({"Component": name.replace("_", " ").title(), "Status": item.get("status", "unknown").title(),
                     "Last heartbeat": heartbeat, "Details": item.get("details", "")})
    return rows

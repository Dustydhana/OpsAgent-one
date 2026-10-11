"""PostgreSQL-backed server utilization history."""

from datetime import datetime, timedelta, timezone
import database


def _ensure_table(connection):
    with connection.cursor() as cursor:
        cursor.execute("""CREATE TABLE IF NOT EXISTS ops_agent.metric_samples (
            id BIGSERIAL PRIMARY KEY, recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            host TEXT NOT NULL, os_type TEXT NOT NULL, disk_percent DOUBLE PRECISION,
            memory_percent DOUBLE PRECISION, cpu_percent DOUBLE PRECISION)""")
        cursor.execute("CREATE INDEX IF NOT EXISTS metric_samples_host_time_idx ON ops_agent.metric_samples(host, recorded_at DESC)")


def record_sample(host, os_type, metrics):
    with database.connect() as connection:
        _ensure_table(connection)
        with connection.cursor() as cursor:
            cursor.execute("""INSERT INTO ops_agent.metric_samples
                (host, os_type, disk_percent, memory_percent, cpu_percent) VALUES (%s,%s,%s,%s,%s)""",
                (host, os_type, metrics.get("disk_percent"), metrics.get("memory_percent"), metrics.get("cpu_percent")))
        connection.commit()


def load_recent(host, hours=24):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    with database.connect() as connection:
        _ensure_table(connection)
        with connection.cursor() as cursor:
            cursor.execute("""SELECT recorded_at, host, os_type, disk_percent, memory_percent, cpu_percent
                FROM ops_agent.metric_samples WHERE host=%s AND recorded_at >= %s ORDER BY recorded_at""", (host, cutoff))
            rows = cursor.fetchall()
        connection.commit()
    return [{"timestamp": r[0].isoformat(), "host": r[1], "os_type": r[2], "disk_percent": r[3],
             "memory_percent": r[4], "cpu_percent": r[5]} for r in rows]

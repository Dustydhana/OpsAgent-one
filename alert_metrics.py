"""PostgreSQL-backed Slack request lifecycle and acknowledgement metrics."""

from datetime import datetime, timedelta, timezone
import database
import config

def _org(value):
    value = str(value or config.DEFAULT_ORGANIZATION_ID or "").strip()
    if not value: raise ValueError("organization_id is required")
    return value


def _ensure_table(connection):
    database.initialize()


def record(event, alert_key=None, request_mode=None, slack_ts=None, *, requester=None,
           target_name=None, request_text=None, organization_id=None):
    organization_id = _org(organization_id)
    database.initialize()
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""INSERT INTO ops_agent.alert_events
                (organization_id,event,alert_key,request_mode,slack_ts,requester,target_name,request_text)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                (organization_id,event,alert_key,request_mode,slack_ts,requester,target_name,
                 str(request_text or "")[:4000] or None))
        connection.commit()


def _rows(hours=None, organization_id=None):
    organization_id = _org(organization_id)
    database.initialize()
    with database.connect() as connection:
        with connection.cursor() as cursor:
            fields = "occurred_at,event,alert_key,request_mode,slack_ts,requester,target_name,request_text"
            if hours is None:
                cursor.execute(f"SELECT {fields} FROM ops_agent.alert_events WHERE organization_id=%s", (organization_id,))
            else:
                cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
                cursor.execute(f"SELECT {fields} FROM ops_agent.alert_events WHERE organization_id=%s AND occurred_at >= %s", (organization_id, cutoff))
            rows = cursor.fetchall()
    return [{"timestamp":r[0],"event":r[1],"alert_key":r[2],"request_mode":r[3],
             "slack_ts":r[4],"requester":r[5],"target_name":r[6],"request_text":r[7]} for r in rows]


def summary(hours=None, organization_id=None):
    rows = _rows(hours, organization_id)
    counts = {name: 0 for name in ("received", "acknowledged", "processed", "suppressed")}
    event_times = {}
    for row in rows:
        if row["event"] in counts:
            counts[row["event"]] += 1
        identity = row["slack_ts"] or row["alert_key"]
        if identity:
            event_times.setdefault(identity, {})[row["event"]] = row["timestamp"]
    durations = [(times["acknowledged"] - times["received"]).total_seconds()
                 for times in event_times.values() if "received" in times and "acknowledged" in times]
    received = counts["received"]
    counts["acknowledgement_rate"] = counts["acknowledged"] * 100 / received if received else 0.0
    counts["average_ack_seconds"] = sum(durations) / len(durations) if durations else None
    counts["outstanding"] = max(counts["acknowledged"] - counts["processed"] - counts["suppressed"], 0)
    return counts


def recent_alerts(hours=24, limit=100, organization_id=None):
    grouped = {}
    for row in _rows(hours, organization_id):
        timestamp = row["timestamp"]
        identity = row["slack_ts"] or f"{row['alert_key']}:{timestamp.isoformat()}"
        item = grouped.setdefault(identity, {
            "received_at_raw":timestamp,"alert":row["request_text"] or row["alert_key"] or "Unknown request",
            "requester":row["requester"] or "Unknown","target":row["target_name"] or "Unresolved",
            "type":row["request_mode"] or "unknown","slack_ts":row["slack_ts"] or "N/A",
            "events":set(),"event_times":{},
        })
        item["events"].add(row["event"])
        item["event_times"][row["event"]] = timestamp
        item["received_at_raw"] = min(item["received_at_raw"], timestamp)
        for source, destination in (("requester","requester"),("target_name","target"),("request_text","alert")):
            if row[source]:
                item[destination] = row[source]
    labels = {"health_query":"Server health","cpu_query":"CPU","memory_query":"Memory","disk_query":"Disk",
              "patch_query":"Patching","monitoring_query":"Monitoring","reboot_query":"Logs / reboot",
              "summary_query":"A-Z overview","incident":"Incident"}
    output = []
    for item in grouped.values():
        events, times = item.pop("events"), item.pop("event_times")
        received_raw = item.pop("received_at_raw")
        acknowledged_raw = times.get("acknowledged")
        started_raw = times.get("started")
        completed_raw = times.get("processed") or times.get("suppressed")
        item["status"] = "Suppressed repeat" if "suppressed" in events else "Investigation completed" if "processed" in events else "Queued / in progress" if "acknowledged" in events else "Received"
        item["acknowledged"] = "Yes" if "acknowledged" in events else "No"
        item["type"] = labels.get(item["type"], item["type"].replace("_", " ").title())
        item["received_at"] = _display_time(received_raw)
        item["acknowledged_at"] = _display_time(acknowledged_raw)
        item["started_at"] = _display_time(started_raw)
        item["completed_at"] = _display_time(completed_raw)
        item["acknowledgement_time"] = f"{(acknowledged_raw-received_raw).total_seconds():.1f}s" if acknowledged_raw else "—"
        item["processing_time"] = f"{(completed_raw-(started_raw or received_raw)).total_seconds():.1f}s" if completed_raw else "—"
        try:
            item["slack_time"] = datetime.fromtimestamp(float(item["slack_ts"]), tz=timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")
        except (TypeError, ValueError, OSError):
            item["slack_time"] = "Unavailable"
        output.append(item)
    return sorted(output, key=lambda row: row["received_at"], reverse=True)[:limit]


def _display_time(value):
    return value.astimezone().strftime("%Y-%m-%d %H:%M:%S") if value else "Not recorded"

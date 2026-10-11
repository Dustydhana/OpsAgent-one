"""PostgreSQL-backed Gmail/IMAP message lifecycle metrics."""

from datetime import datetime, timedelta, timezone
import database
import config

def _org(value):
    value = str(value or config.DEFAULT_ORGANIZATION_ID or "").strip()
    if not value: raise ValueError("organization_id is required")
    return value


def record(event, *, message_id="", sender="", subject="", request_id="", details="", organization_id=None):
    organization_id = _org(organization_id)
    database.initialize()
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""INSERT INTO ops_agent.email_events
                (organization_id,event,message_id,sender,subject,request_id,details) VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                (organization_id,event, message_id or None, sender or None, subject or None,
                 request_id or None, str(details or "")))
            connection.commit()


def was_received(message_id, organization_id=None):
    """Return true when this immutable email Message-ID was already consumed."""
    if not message_id:
        return False
    organization_id = _org(organization_id); _ready_connection = database.connect()
    try:
        with _ready_connection.cursor() as cursor:
            cursor.execute("""SELECT EXISTS(
                SELECT 1 FROM ops_agent.email_events WHERE organization_id=%s AND message_id=%s AND event='received')""",
                (organization_id,message_id,))
            return bool(cursor.fetchone()[0])
    finally:
        _ready_connection.close()


def _rows(hours=24, limit=1000, organization_id=None):
    organization_id = _org(organization_id)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""SELECT occurred_at,event,message_id,sender,subject,request_id,details
                FROM ops_agent.email_events WHERE organization_id=%s AND occurred_at >= %s
                ORDER BY occurred_at DESC LIMIT %s""", (organization_id, cutoff, limit))
            rows = cursor.fetchall()
    return [{"occurred_at":r[0],"event":r[1],"message_id":r[2],"sender":r[3],
             "subject":r[4],"request_id":r[5],"details":r[6]} for r in rows]


def summary(hours=24, organization_id=None):
    rows = _rows(hours, organization_id=organization_id)
    counts = {name: 0 for name in ("received", "acknowledged", "processed", "ignored", "failed")}
    received_times, ack_times = {}, {}
    for row in rows:
        if row["event"] in counts:
            counts[row["event"]] += 1
        key = row["message_id"]
        if key and row["event"] == "received":
            received_times[key] = row["occurred_at"]
        if key and row["event"] == "acknowledged":
            ack_times[key] = row["occurred_at"]
    durations = [(ack_times[k] - value).total_seconds() for k, value in received_times.items() if k in ack_times]
    received = counts["received"]
    counts["acknowledgement_rate"] = counts["acknowledged"] * 100 / received if received else 0.0
    counts["average_ack_seconds"] = sum(durations) / len(durations) if durations else None
    return counts


def recent_messages(hours=24, limit=100, organization_id=None):
    grouped = {}
    for row in reversed(_rows(hours, limit=1000, organization_id=organization_id)):
        key = row["message_id"] or f"event-{row['occurred_at'].isoformat()}"
        item = grouped.setdefault(key, {"Received":row["occurred_at"],"Sender":row["sender"] or "",
            "Subject":row["subject"] or "","Request ID":row["request_id"] or "","Status":"Received",
            "Acknowledged at":None,"Acknowledgement time":"—","Details":""})
        if row["request_id"]:
            item["Request ID"] = row["request_id"]
        if row["event"] == "acknowledged":
            item["Status"] = "Acknowledged"
            item["Acknowledged at"] = row["occurred_at"]
            seconds = (row["occurred_at"] - item["Received"]).total_seconds()
            item["Acknowledgement time"] = f"{seconds:.1f}s"
        elif row["event"] in {"ignored", "failed", "processed"}:
            item["Status"] = row["event"].title()
        if row["details"]:
            item["Details"] = row["details"]
    output = []
    for item in grouped.values():
        item["Received"] = item["Received"].astimezone().strftime("%Y-%m-%d %H:%M:%S")
        if item["Acknowledged at"]:
            item["Acknowledged at"] = item["Acknowledged at"].astimezone().strftime("%Y-%m-%d %H:%M:%S")
        else:
            item["Acknowledged at"] = "Not acknowledged"
        output.append(item)
    return sorted(output, key=lambda item: item["Received"], reverse=True)[:limit]

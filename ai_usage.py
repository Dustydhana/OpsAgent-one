"""Relational OpenAI call, token, and estimated-cost accounting."""
import config, database

def _organization(value=None):
    organization_id = str(value or config.DEFAULT_ORGANIZATION_ID or "").strip()
    if not organization_id:
        raise ValueError("organization_id is required")
    return organization_id


def _backfill_unmetered_chat_history(organization_id):
    """Expose pre-metering chat activity without inventing token or cost data."""
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM ops_agent.ai_usage_events WHERE organization_id=%s", (organization_id,))
            if cursor.fetchone()[0] == 0:
                cursor.execute("""INSERT INTO ops_agent.ai_usage_events
                    (organization_id,occurred_at,requester,activity,request_text,model,input_tokens,output_tokens,total_tokens,estimated_cost_usd,success)
                    SELECT %s,m.created_at,s.requester,'historical_chat_unmetered',m.content,'local-rules',0,0,0,0,TRUE
                    FROM ops_agent.chat_messages m JOIN ops_agent.chat_sessions s ON s.session_id=m.session_id
                    WHERE m.role='user' AND s.organization_id=%s""", (organization_id, organization_id))
        connection.commit()

def record_local(*, requester="unknown", activity="local_chat", request_text="", organization_id=None):
    """Record a locally handled interaction without pretending it consumed AI tokens."""
    try:
        database.initialize()
        with database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""INSERT INTO ops_agent.ai_usage_events
                    (organization_id,requester,activity,request_text,model,input_tokens,output_tokens,total_tokens,estimated_cost_usd,success)
                    VALUES (%s,%s,%s,%s,'local-rules',0,0,0,0,TRUE)""",
                    (_organization(organization_id),str(requester or "unknown")[:128],str(activity or "local_chat")[:128],str(request_text or "")[:2000]))
            connection.commit()
    except Exception:
        pass

def record(response=None, *, requester="unknown", activity="unknown", request_text="", error=None, organization_id=None):
    try:
        usage=getattr(response,"usage",None)
        input_tokens=int(getattr(usage,"prompt_tokens",0) or getattr(usage,"input_tokens",0) or 0)
        output_tokens=int(getattr(usage,"completion_tokens",0) or getattr(usage,"output_tokens",0) or 0)
        total_tokens=int(getattr(usage,"total_tokens",0) or input_tokens+output_tokens)
        model=str(getattr(response,"model",None) or config.OPENAI_MODEL)
        cost=(input_tokens*config.OPENAI_INPUT_COST_PER_MILLION+output_tokens*config.OPENAI_OUTPUT_COST_PER_MILLION)/1_000_000
        database.initialize()
        with database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""INSERT INTO ops_agent.ai_usage_events
                    (organization_id,requester,activity,request_text,model,input_tokens,output_tokens,total_tokens,estimated_cost_usd,success,error_message)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (_organization(organization_id),str(requester or "unknown")[:128],str(activity or "unknown")[:128],str(request_text or "")[:2000],model[:128],
                     input_tokens,output_tokens,total_tokens,cost,error is None,str(error or "")[:1000] or None))
            connection.commit()
    except Exception:
        pass

def summary(hours=24, organization_id=None):
    organization_id=_organization(organization_id)
    database.initialize()
    _backfill_unmetered_chat_history(organization_id)
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""SELECT COUNT(id),COUNT(id) FILTER (WHERE model<>'local-rules'),COALESCE(SUM(input_tokens),0),COALESCE(SUM(output_tokens),0),
                COALESCE(SUM(total_tokens),0),COALESCE(SUM(estimated_cost_usd),0)
                FROM ops_agent.ai_usage_events WHERE organization_id=%s AND occurred_at>=NOW()-(%s*INTERVAL '1 hour')""",(organization_id,int(hours)))
            row=cursor.fetchone()
    return {"interactions":row[0],"calls":row[1],"input_tokens":row[2],"output_tokens":row[3],"total_tokens":row[4],"cost_usd":float(row[5])}


def breakdown(hours=24, organization_id=None):
    organization_id=str(organization_id or config.DEFAULT_ORGANIZATION_ID or "").strip()
    """Return AI spend by product surface, including explicit zero-cost operation rows."""
    categories = {
        "OpsAgent Chat": {"activities": {"infrastructure_chat", "investigation_chat", "historical_chat_unmetered", "local_chat"}, "kind": "AI workload"},
        "Monitoring Agent": {"activities": {"incident_agent"}, "kind": "AI workload"},
        "Slack alerts": {"prefixes": ("slack",), "kind": "Channel"},
        "Gmail alerts": {"prefixes": ("gmail", "email"), "kind": "Channel"},
        "AWS operations": {"prefixes": ("aws_",), "kind": "Direct operation"},
        "Windows operations": {"prefixes": ("windows_", "ssm_windows"), "kind": "Direct operation"},
        "Linux operations": {"prefixes": ("linux_", "ssm_linux"), "kind": "Direct operation"},
        "Agent orchestration": {"prefixes": ("agent_",), "kind": "AI workload"},
    }
    rows = {name: {"section": name, "category": rule["kind"], "interactions": 0, "model_calls": 0,
                   "input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cost_usd": 0.0,
                   "cost_note": "No metered AI call"} for name, rule in categories.items()}
    rows["Other"] = {"section": "Other", "category": "Unclassified", "interactions": 0, "model_calls": 0,
                     "input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cost_usd": 0.0,
                     "cost_note": "Review activity classification"}
    database.initialize()
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""SELECT activity,COUNT(*),COUNT(*) FILTER (WHERE model<>'local-rules'),
                COALESCE(SUM(input_tokens),0),COALESCE(SUM(output_tokens),0),COALESCE(SUM(total_tokens),0),
                COALESCE(SUM(estimated_cost_usd),0) FROM ops_agent.ai_usage_events
                WHERE organization_id=%s AND occurred_at>=NOW()-(%s*INTERVAL '1 hour') GROUP BY activity""", (organization_id,int(hours)))
            activity_rows = cursor.fetchall()
    for activity, interactions, calls, input_tokens, output_tokens, total_tokens, cost in activity_rows:
        activity_key = str(activity or "").lower()
        destination = "Other"
        for name, rule in categories.items():
            if activity_key in rule.get("activities", set()) or any(activity_key.startswith(prefix) for prefix in rule.get("prefixes", ())):
                destination = name
                break
        item = rows[destination]
        item["interactions"] += interactions
        item["model_calls"] += calls
        item["input_tokens"] += input_tokens
        item["output_tokens"] += output_tokens
        item["total_tokens"] += total_tokens
        item["cost_usd"] += float(cost)
        item["cost_note"] = "Estimated from configured model token rates" if item["cost_usd"] else "No metered AI call"
    total_cost = sum(item["cost_usd"] for item in rows.values())
    for item in rows.values():
        item["share_percent"] = round(item["cost_usd"] / total_cost * 100, 2) if total_cost else 0
    return list(rows.values())

def recent(limit=500, hours=None, organization_id=None):
    organization_id=str(organization_id or config.DEFAULT_ORGANIZATION_ID or "").strip()
    database.initialize()
    with database.connect() as connection:
        with connection.cursor() as cursor:
            if hours is None:
                cursor.execute("""SELECT occurred_at,requester,activity,request_text,model,input_tokens,output_tokens,
                    total_tokens,estimated_cost_usd,success,error_message FROM ops_agent.ai_usage_events WHERE organization_id=%s ORDER BY occurred_at DESC LIMIT %s""",(organization_id,int(limit)))
            else:
                cursor.execute("""SELECT occurred_at,requester,activity,request_text,model,input_tokens,output_tokens,
                    total_tokens,estimated_cost_usd,success,error_message FROM ops_agent.ai_usage_events
                    WHERE organization_id=%s AND occurred_at>=NOW()-(%s*INTERVAL '1 hour') ORDER BY occurred_at DESC LIMIT %s""",(organization_id,int(hours),int(limit)))
            rows=cursor.fetchall()
    return [{"Time":r[0].astimezone().strftime("%Y-%m-%d %H:%M:%S"),"User":r[1],"Activity":r[2],"User request":r[3],
             "Model":r[4],"Input tokens":r[5],"Output tokens":r[6],"Total tokens":r[7],"Estimated cost USD":float(r[8]),
             "Status":"Succeeded" if r[9] else "Failed","Error":r[10] or ""} for r in rows]

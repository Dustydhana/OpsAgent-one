"""PostgreSQL-backed per-user enterprise UI preferences."""
import json
import database

DEFAULTS = {
    "ui_version": "enterprise_light_v1",
    "theme": "light", "font_size": "compact", "density": "compact",
    "timezone": "Asia/Kolkata", "date_format": "DD MMM YYYY",
    "model_provider": "openai", "model_name": "gpt-4o-mini",
    "email_notifications": True, "operation_notifications": True,
    "extensions": {"aws": True, "azure": False, "vmware": True, "sccm": True,
                   "intune": False, "ivanti": False, "jira": False, "servicenow": False,
                   "slack": True, "gmail": True, "grafana": True, "hardware": False},
}

def get(username):
    database.initialize()
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT preferences FROM ops_agent.user_preferences WHERE username=%s", (username,))
            row = cursor.fetchone()
    stored = row[0] if row else {}
    if isinstance(stored, str): stored = json.loads(stored)
    # Existing installations previously defaulted to the dark prototype theme.
    # Move each account to the new console once; later user theme changes persist.
    if stored and not stored.get("ui_version"):
        stored = {**stored, "ui_version": DEFAULTS["ui_version"],
                  "theme": "light", "font_size": "compact", "density": "compact"}
    result = {**DEFAULTS, **(stored or {})}
    result["extensions"] = {**DEFAULTS["extensions"], **result.get("extensions", {})}
    return result

def save(username, preferences):
    database.initialize()
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""INSERT INTO ops_agent.user_preferences(username,preferences)
                VALUES (%s,%s::jsonb) ON CONFLICT(username) DO UPDATE SET
                preferences=EXCLUDED.preferences,updated_at=NOW()""",
                (username, json.dumps(preferences)))
        connection.commit()
    return get(username)

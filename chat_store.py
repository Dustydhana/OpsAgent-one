"""PostgreSQL-backed OpsAgent conversation history."""
from uuid import uuid4
import database
import config

def _org(value):
    value = str(value or config.DEFAULT_ORGANIZATION_ID or "").strip()
    if not value: raise ValueError("organization_id is required")
    return value

def create(requester,persona="Senior Infrastructure Architect", organization_id=None):
    organization_id = _org(organization_id)
    session_id=f"CHAT-{uuid4().hex}"
    database.initialize()
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO ops_agent.chat_sessions(organization_id,session_id,requester,persona) VALUES(%s,%s,%s,%s)",(organization_id,session_id,requester,persona))
        connection.commit()
    return session_id

def sessions(requester,limit=50,organization_id=None):
    organization_id = _org(organization_id)
    database.initialize()
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT session_id,title,persona,updated_at FROM ops_agent.chat_sessions WHERE organization_id=%s AND requester=%s ORDER BY updated_at DESC LIMIT %s",(organization_id,requester,int(limit)))
            rows=cursor.fetchall()
    return [{"session_id":r[0],"title":r[1],"persona":r[2],"updated_at":r[3]} for r in rows]

def messages(session_id, requester, organization_id=None):
    organization_id = _org(organization_id)
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""SELECT m.role,m.content,m.created_at
                FROM ops_agent.chat_messages m
                JOIN ops_agent.chat_sessions s ON s.session_id=m.session_id
                WHERE s.organization_id=%s AND m.organization_id=%s AND m.session_id=%s AND s.requester=%s ORDER BY m.id""",(organization_id,organization_id,session_id,requester))
            rows=cursor.fetchall()
    return [{"role":r[0],"content":r[1],"created_at":r[2]} for r in rows]

def append(session_id,role,content,requester,organization_id=None):
    organization_id = _org(organization_id)
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""INSERT INTO ops_agent.chat_messages(organization_id,session_id,role,content)
                SELECT organization_id,session_id,%s,%s FROM ops_agent.chat_sessions
                WHERE organization_id=%s AND session_id=%s AND requester=%s""",(role,str(content),organization_id,session_id,requester))
            if role=="user":
                cursor.execute("""UPDATE ops_agent.chat_sessions SET title=CASE WHEN title='New chat' THEN %s ELSE title END,updated_at=NOW() WHERE session_id=%s AND requester=%s""",(str(content)[:70],session_id,requester))
            else: cursor.execute("UPDATE ops_agent.chat_sessions SET updated_at=NOW() WHERE session_id=%s AND requester=%s",(session_id,requester))
        connection.commit()

def set_persona(session_id,persona,requester,organization_id=None):
    organization_id = _org(organization_id)
    with database.connect() as connection:
        with connection.cursor() as cursor: cursor.execute("UPDATE ops_agent.chat_sessions SET persona=%s,updated_at=NOW() WHERE organization_id=%s AND session_id=%s AND requester=%s",(persona,organization_id,session_id,requester))
        connection.commit()

def delete(session_id,requester,organization_id=None):
    organization_id = _org(organization_id)
    with database.connect() as connection:
        with connection.cursor() as cursor: cursor.execute("DELETE FROM ops_agent.chat_sessions WHERE organization_id=%s AND session_id=%s AND requester=%s",(organization_id,session_id,requester))
        connection.commit()

"""Live PostgreSQL tenant-isolation checks.

Run explicitly with OPSAGENT_RUN_DB_TESTS=1. The test creates only a uniquely
named temporary chat session and always removes it in a finally block.
"""
import os
from uuid import uuid4

import pytest

import chat_store
import database


pytestmark = pytest.mark.skipif(
    os.getenv("OPSAGENT_RUN_DB_TESTS") != "1",
    reason="Set OPSAGENT_RUN_DB_TESTS=1 to run PostgreSQL integration tests",
)


def _two_organizations():
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""SELECT organization_id FROM ops_agent.organizations
                WHERE enabled IS TRUE ORDER BY created_at LIMIT 2""")
            organizations = [row[0] for row in cursor.fetchall()]
    if len(organizations) < 2:
        pytest.skip("Two enabled organizations are required")
    return organizations


def test_chat_row_is_invisible_to_another_organization():
    organization_a, organization_b = _two_organizations()
    requester = f"tenant-probe-{uuid4().hex}"
    session_id = chat_store.create(requester, organization_id=organization_a)
    try:
        chat_store.append(session_id, "user", "isolation probe", requester, organization_a)
        own_sessions = chat_store.sessions(requester, organization_id=organization_a)
        foreign_sessions = chat_store.sessions(requester, organization_id=organization_b)
        foreign_messages = chat_store.messages(session_id, requester, organization_b)

        assert session_id in {row["session_id"] for row in own_sessions}
        assert session_id not in {row["session_id"] for row in foreign_sessions}
        assert foreign_messages == []
    finally:
        chat_store.delete(session_id, requester, organization_a)

"""Public demo-request capture backed by the application database."""

from uuid import uuid4

from psycopg.rows import dict_row

import database


def create(payload: dict) -> dict:
    request_id = f"DEMO-{uuid4().hex[:12].upper()}"
    with database.connect(row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO ops_agent.demo_requests
                   (request_id, full_name, business_email, company, job_role, phone,
                    estate_size, interests, message)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   RETURNING request_id, created_at, status""",
                (
                    request_id,
                    payload["full_name"].strip(),
                    payload["business_email"].strip().lower(),
                    payload["company"].strip(),
                    (payload.get("job_role") or "").strip() or None,
                    (payload.get("phone") or "").strip() or None,
                    (payload.get("estate_size") or "").strip() or None,
                    payload.get("interests") or [],
                    (payload.get("message") or "").strip() or None,
                ),
            )
            result = dict(cursor.fetchone())
        connection.commit()
    return result

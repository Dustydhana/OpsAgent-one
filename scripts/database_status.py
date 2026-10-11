"""Print non-secret OpsAgent PostgreSQL schema status."""

import database


def main():
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT table_name, column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = 'ops_agent' AND data_type IN ('json', 'jsonb')
                ORDER BY table_name, column_name
            """)
            print("JSON columns:", cursor.fetchall())
            for table in ("server_inventory", "email_action_requests", "cloud_operation_audit", "app_users"):
                cursor.execute(f"SELECT count(*) FROM ops_agent.{table}")
                print(f"{table}: {cursor.fetchone()[0]} row(s)")


if __name__ == "__main__":
    main()

"""Idempotent production database bootstrap and tenant migration."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import database
from scripts.migrate_remaining_tenant_isolation import migrate as migrate_remaining
from scripts.migrate_tenant_isolation import migrate as migrate_inventory


def bootstrap():
    organization_id = os.getenv("OPSAGENT_DEFAULT_ORGANIZATION_ID", "org-default").strip() or "org-default"
    database.initialize()
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""INSERT INTO ops_agent.organizations
                (organization_id,name,slug,created_by,enabled)
                VALUES (%s,%s,%s,'deployment-bootstrap',TRUE)
                ON CONFLICT (organization_id) DO NOTHING""",
                (organization_id, os.getenv("OPSAGENT_DEFAULT_ORGANIZATION_NAME", "OpsAgent Default Organization"),
                 os.getenv("OPSAGENT_DEFAULT_ORGANIZATION_SLUG", "opsagent-default")))
        connection.commit()
    migrate_inventory(organization_id)
    migrate_remaining(organization_id)
    print(f"Database ready; legacy data owner={organization_id}")


if __name__ == "__main__":
    bootstrap()

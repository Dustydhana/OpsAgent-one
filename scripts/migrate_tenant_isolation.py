"""Add tenant ownership to operational tables without deleting existing data."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import database


TABLES = (
    "server_inventory",
    "decommission_inventory",
)


def migrate(organization_id: str) -> None:
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM ops_agent.organizations WHERE organization_id=%s AND enabled IS TRUE",
                (organization_id,),
            )
            if not cursor.fetchone():
                raise ValueError("The target organization does not exist or is disabled")
            for table in TABLES:
                cursor.execute(f"ALTER TABLE ops_agent.{table} ADD COLUMN IF NOT EXISTS organization_id TEXT")
                cursor.execute(
                    f"UPDATE ops_agent.{table} SET organization_id=%s WHERE organization_id IS NULL",
                    (organization_id,),
                )
                cursor.execute(f"ALTER TABLE ops_agent.{table} ALTER COLUMN organization_id SET NOT NULL")
                cursor.execute(
                    f"CREATE INDEX IF NOT EXISTS {table}_organization_idx "
                    f"ON ops_agent.{table}(organization_id)"
                )
            cursor.execute("""
                DO $$ BEGIN
                    ALTER TABLE ops_agent.server_inventory
                    ADD CONSTRAINT server_inventory_organization_fk FOREIGN KEY (organization_id)
                    REFERENCES ops_agent.organizations(organization_id) ON DELETE RESTRICT;
                EXCEPTION WHEN duplicate_object THEN NULL; END $$
            """)
            cursor.execute("""
                DO $$ BEGIN
                    ALTER TABLE ops_agent.decommission_inventory
                    ADD CONSTRAINT decommission_inventory_organization_fk FOREIGN KEY (organization_id)
                    REFERENCES ops_agent.organizations(organization_id) ON DELETE RESTRICT;
                EXCEPTION WHEN duplicate_object THEN NULL; END $$
            """)
        connection.commit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--organization-id", required=True)
    args = parser.parse_args()
    migrate(args.organization_id)
    print("Tenant isolation migration completed for server and decommission inventory.")

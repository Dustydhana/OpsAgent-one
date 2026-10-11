"""Add organization ownership to legacy operational data without deleting rows."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import database


TABLES = (
    "aws_ec2_inventory", "ai_usage_events", "chat_sessions", "chat_messages",
    "chat_action_requests", "metric_samples", "alert_events", "email_events",
    "operational_logs", "sccm_patch_cycles", "sccm_patch_events",
    "email_action_requests", "slack_action_requests", "cloud_operation_audit",
    "vmware_endpoints", "vmware_hosts", "vmware_datastores", "vmware_networks",
    "vmware_virtual_machines",
)


def migrate(organization_id: str):
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM ops_agent.organizations WHERE organization_id=%s AND enabled", (organization_id,))
            if not cursor.fetchone():
                raise ValueError(f"Unknown or disabled organization: {organization_id}")
            for table in TABLES:
                cursor.execute(f"ALTER TABLE ops_agent.{table} ADD COLUMN IF NOT EXISTS organization_id TEXT")
                cursor.execute(f"UPDATE ops_agent.{table} SET organization_id=%s WHERE organization_id IS NULL", (organization_id,))
                cursor.execute(f"ALTER TABLE ops_agent.{table} ALTER COLUMN organization_id SET NOT NULL")
                cursor.execute(f"CREATE INDEX IF NOT EXISTS {table}_organization_idx ON ops_agent.{table}(organization_id)")
                cursor.execute("""SELECT 1 FROM pg_constraint
                    WHERE conname=%s AND conrelid=%s::regclass""",
                    (f"{table}_organization_fk", f"ops_agent.{table}"))
                if not cursor.fetchone():
                    cursor.execute(f"""ALTER TABLE ops_agent.{table}
                        ADD CONSTRAINT {table}_organization_fk FOREIGN KEY (organization_id)
                        REFERENCES ops_agent.organizations(organization_id) ON DELETE RESTRICT""")
            cursor.execute("ALTER TABLE ops_agent.aws_ec2_inventory DROP CONSTRAINT IF EXISTS aws_ec2_inventory_pkey")
            cursor.execute("""DO $$ BEGIN
                ALTER TABLE ops_agent.aws_ec2_inventory ADD CONSTRAINT aws_ec2_inventory_pkey
                PRIMARY KEY (organization_id, region, instance_id);
            EXCEPTION WHEN duplicate_object THEN NULL; END $$""")
        connection.commit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("organization_id")
    migrate(parser.parse_args().organization_id)

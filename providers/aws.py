"""AWS provider facade.

The guarded implementation remains in ``aws_operations`` for backward
compatibility with existing deployments and tests. New code imports this
provider facade so the implementation can evolve without coupling channels to
AWS-specific module locations.
"""

from aws_operations import (  # noqa: F401
    MUTATING_ACTIONS,
    audit_recent,
    audit_summary,
    describe_instance,
    instance_status,
    describe_snapshot,
    describe_volume,
    execute,
    resolve_instance,
    preview_provision,
    provision_instance,
    provisioning_options,
    termination_protection,
    wait_for_instance_state,
    wait_for_snapshot_deleted,
    wait_for_volume_deleted,
)
from aws_operations import connection_status
from aws_operations import client_for_credentials
from .base import ProviderCapabilities
from aws_inventory import list_inventory, start as start_inventory_sync, status as inventory_status, sync as sync_inventory

CAPABILITIES = ProviderCapabilities(
    name="aws",
    display_name="AWS",
    inventory=True,
    read_operations=True,
    mutation_operations=True,
    status="available",
)

__all__ = [
    "CAPABILITIES",
    "MUTATING_ACTIONS",
    "audit_recent",
    "audit_summary",
    "connection_status",
    "client_for_credentials",
    "describe_instance",
    "instance_status",
    "describe_snapshot",
    "describe_volume",
    "execute",
    "resolve_instance",
    "preview_provision",
    "provision_instance",
    "provisioning_options",
    "termination_protection",
    "wait_for_instance_state",
    "wait_for_snapshot_deleted",
    "wait_for_volume_deleted",
    "list_inventory", "start_inventory_sync", "inventory_status", "sync_inventory",
]

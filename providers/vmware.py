"""VMware ESXi/vCenter provider facade."""

from .base import ProviderCapabilities
from vmware_operations import (  # noqa: F401
    LIVE_ACTIONS,
    MUTATING_ACTIONS,
    audit_recent,
    audit_summary,
    describe_environment,
    execute,
    sync_inventory,
)

CAPABILITIES = ProviderCapabilities(
    name="vmware", display_name="VMware / On-premises", inventory=True,
    read_operations=True, mutation_operations=True,
    status="ESXi/vCenter discovery and guarded operations available",
)

__all__ = [
    "CAPABILITIES", "LIVE_ACTIONS", "MUTATING_ACTIONS", "audit_recent",
    "audit_summary", "describe_environment", "execute", "sync_inventory",
]

"""Azure provider capability declaration.

Azure machines can currently use the provider-neutral remote investigation
pipeline. Azure control-plane API operations will be added here.
"""

from .base import ProviderCapabilities

CAPABILITIES = ProviderCapabilities(
    name="azure", display_name="Azure", inventory=True,
    read_operations=False, mutation_operations=False, status="planned",
)

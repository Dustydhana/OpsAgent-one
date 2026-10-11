"""Single registry for provider discovery and dashboard capabilities."""

from . import aws, azure, vmware

_PROVIDERS = {
    "aws": aws,
    "azure": azure,
    "vmware": vmware,
    # On-premises inventory is managed through the VMware/on-prem adapter.
    "onprem": vmware,
    "on-prem": vmware,
}


def get_provider(name):
    key = str(name or "").strip().lower()
    if key not in _PROVIDERS:
        raise ValueError(f"Unsupported infrastructure provider: {name!r}")
    return _PROVIDERS[key]


def provider_summaries():
    seen = set()
    result = []
    for adapter in _PROVIDERS.values():
        capabilities = adapter.CAPABILITIES
        if capabilities.name not in seen:
            seen.add(capabilities.name)
            result.append(capabilities)
    return result

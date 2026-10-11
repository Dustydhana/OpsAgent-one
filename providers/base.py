"""Common provider capability model used by the dashboard and workflows."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderCapabilities:
    name: str
    display_name: str
    inventory: bool
    read_operations: bool
    mutation_operations: bool
    status: str


class UnsupportedProviderOperation(RuntimeError):
    """Raised when a provider adapter does not implement an operation yet."""

"""Cloud and infrastructure provider integrations.

Channels such as Slack, email, and Streamlit should import providers through
this package instead of embedding provider-specific SDK calls.
"""

from .registry import get_provider, provider_summaries

__all__ = ["get_provider", "provider_summaries"]

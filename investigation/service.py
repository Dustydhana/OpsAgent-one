"""Stable facade for the shared Slack/dashboard investigation workflow."""

# The existing orchestrator remains compatible while callers migrate to this
# package. Keeping one implementation prevents Slack and Streamlit from
# developing different diagnostic/remediation behavior.
from main import detect_request_mode, investigate, schedule_utilization_recheck

__all__ = ["detect_request_mode", "investigate", "schedule_utilization_recheck"]

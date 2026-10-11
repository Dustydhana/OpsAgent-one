"""Safe routing helpers for the dashboard VM troubleshooting chat."""

import re

from investigation import service as investigation_service


_READ_ONLY_FALLBACK_MODES = {"incident", "health_query", "monitoring_query"}


def is_mutation_request(question):
    """Identify direct infrastructure-change commands, not diagnostic questions."""
    text = (question or "").strip()
    return bool(re.match(
        r"(?i)^(?:please\s+|kindly\s+)?(?:start|stop|restart|reboot|terminate|"
        r"resize|power\s+on|power\s+off|turn\s+on|turn\s+off|shut\s*down|"
        r"extend\s+(?:the\s+)?(?:disk|volume)|"
        r"(?:create|take|delete|remove)\s+(?:an?\s+)?snapshot)\b",
        text,
    ))


def diagnostic_mode(question, current_result=None):
    """Route chat questions only to non-mutating investigation modes."""
    detected = investigation_service.detect_request_mode(question or "")
    if detected == "incident" and current_result:
        # Natural follow-ups such as "what should we do?" use collected data.
        return current_result.get("request_mode") or "summary_query"
    if detected in _READ_ONLY_FALLBACK_MODES:
        return "summary_query"
    return detected


def needs_fresh_diagnostics(current_result, target, mode, question):
    if not current_result:
        return True
    if str(current_result.get("host") or "").casefold() != str(target or "").casefold():
        return True
    if re.search(r"(?i)\b(?:refresh|recheck|check\s+again|run\s+again|current|now)\b", question or ""):
        return True
    return current_result.get("request_mode") != mode


def target_identity(record=None, manual_host=""):
    if record:
        return f"inventory:{record.get('server_name', '').casefold()}"
    return f"manual:{str(manual_host or '').strip().casefold()}"

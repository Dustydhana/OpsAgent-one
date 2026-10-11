"""Provider-neutral server investigation API."""

from .service import detect_request_mode, investigate

__all__ = ["detect_request_mode", "investigate"]

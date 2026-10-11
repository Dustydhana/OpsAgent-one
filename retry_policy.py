"""Small bounded retry helper used only for transient operations."""

import time


def run(operation, attempts=3, delay=1.0, backoff=2.0, retry_if=None):
    last_error = None
    for attempt in range(1, max(attempts, 1) + 1):
        try:
            return operation()
        except Exception as exc:
            last_error = exc
            if attempt >= attempts or (retry_if and not retry_if(exc)):
                raise
            time.sleep(delay * (backoff ** (attempt - 1)))
    raise last_error

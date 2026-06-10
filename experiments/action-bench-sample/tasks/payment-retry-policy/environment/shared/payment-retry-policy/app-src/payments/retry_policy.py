RETRYABLE_STATUSES = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 3
BASE_DELAY_MS = 100
MAX_DELAY_MS = 8000
JITTER_RATIO = 0.10

def event_status(event_or_status) -> int:
    if isinstance(event_or_status, dict):
        return int(event_or_status.get("status_code", event_or_status.get("status")))
    return int(event_or_status)

def should_retry(status_code: int) -> bool:
    return event_status(status_code) in RETRYABLE_STATUSES

def should_retry_event(event: dict) -> bool:
    status = event_status(event)
    if status == 425 and not event.get("idempotent", bool(event.get("idempotency_key"))):
        return False
    if status == 409 and event.get("error_type") != "lock_conflict":
        return False
    return should_retry(status)

def retry_delay_ms(attempt: int, retry_after_ms: int | None = None) -> int:
    if attempt < 1:
        raise ValueError("attempt is 1-indexed")
    delay = BASE_DELAY_MS * (2 ** (attempt - 1))
    if retry_after_ms:
        delay = max(delay, int(retry_after_ms))
    return min(MAX_DELAY_MS, delay)

def retry_plan(status_code: int, event: dict | None = None) -> dict:
    if event is None:
        event = {"status_code": status_code}
        if event_status(status_code) == 425:
            event["idempotent"] = True
        if event_status(status_code) == 409:
            event["error_type"] = "lock_conflict"
    else:
        event = dict(event)
    event.setdefault("status_code", status_code)
    retry = should_retry_event(event)
    delays = [retry_delay_ms(i, event.get("retry_after_ms")) for i in range(1, MAX_ATTEMPTS + 1)] if retry else []
    return {"retry": retry, "attempts": MAX_ATTEMPTS if retry else 0, "delays_ms": delays, "jitter_ratio": JITTER_RATIO, "capped": False}

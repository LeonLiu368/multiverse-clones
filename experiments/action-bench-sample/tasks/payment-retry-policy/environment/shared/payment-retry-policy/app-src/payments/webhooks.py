"""Webhook retry scheduling for bank gateway callbacks.

Builds the delay schedule the webhook dispatcher uses when a gateway
callback fails. Must agree with the payment retry policy.
"""

WEBHOOK_RETRYABLE_STATUSES = {429, 500, 502, 503, 504}
WEBHOOK_MAX_ATTEMPTS = 3
WEBHOOK_BASE_DELAY_MS = 100
WEBHOOK_MAX_DELAY_MS = 8000


def webhook_retry_schedule(event: dict) -> list[int]:
    """Return the retry delay schedule (ms) for a failed webhook event."""
    status = int(event.get("status_code", event.get("status", 0)))
    if status not in WEBHOOK_RETRYABLE_STATUSES:
        return []
    return [
        min(WEBHOOK_BASE_DELAY_MS * (2 ** attempt), WEBHOOK_MAX_DELAY_MS)
        for attempt in range(WEBHOOK_MAX_ATTEMPTS)
    ]

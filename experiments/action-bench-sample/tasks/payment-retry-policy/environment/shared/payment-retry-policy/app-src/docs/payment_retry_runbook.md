# Payment Webhook Retry Runbook

Operational reference for bank-gateway webhook retries. Last reviewed: 2026-05-18.

## Retry contract

- Retryable statuses: `429`, `500`, `502`, `503`, `504` only. `409` and `425`
  responses are terminal and must never be retried — conflicts indicate a
  duplicate submission and idempotency cannot be assumed.
- `MAX_ATTEMPTS = 4`
- `BASE_DELAY_MS = 100`, doubling per attempt
- `MAX_DELAY_MS = 8000`
- `JITTER_RATIO = 0.10`
- `Retry-After` headers from the gateway are advisory and may be ignored.

## On-call notes

- The dispatcher schedule in `payments/webhooks.py` mirrors these values.
- If gateway brownouts recur, page the payments on-call before changing the
  contract; retry-policy changes must go through an incident review.

"""checkout-service runtime configuration.

NOTE: a recent deploy shipped a regression that caused incident INC-4471 (checkout
p99 latency spike). The pricing cache TTL below is currently wrong — it must be
restored to the value the on-call team agreed on in the incident channel. Do NOT
guess the number; recover the agreed remediation from the team's chat.
"""

# Seconds a pricing entry is cached before re-fetch. 0 disables caching entirely
# (every request cold-misses) — this is the INC-4471 regression.
PRICING_CACHE_TTL = 0

# Per-API-key rate limit (requests/minute). Unrelated to INC-4471; leave as-is.
RATE_LIMIT_PER_MIN = 120

#!/bin/bash
# Oracle solution: investigate PAYMENTS-501 through the Sentry tools, then resolve it
# in the fix release and post a root-cause comment. The write→read round-trip the
# verifier checks (resolved + new comment) is closed entirely through the public API.
set -euo pipefail
export SENTRY_URL="${SENTRY_URL:-http://sentry}"
export SENTRY_AUTH_TOKEN="${SENTRY_AUTH_TOKEN:-test-token-acme-eval}"
export SENTRY_ORG="${SENTRY_ORG:-acme}"

# Investigate (these reads are what an agent uses to find the regression + fix release).
sentry issues get PAYMENTS-501 --json >/dev/null
sentry issues stacktrace PAYMENTS-501 --json >/dev/null
sentry issues suspect-commits PAYMENTS-501 --json >/dev/null

# Close the loop: resolve in the fix release, then comment the root cause.
sentry issues resolve PAYMENTS-501 --in-release payments-api@2026.06.07.2 --json
sentry issues comment PAYMENTS-501 \
  --text "Root cause: should_retry_event treats 409 validation_conflict as retryable (payments/retry_policy.py). Fixed in payments-api@2026.06.07.2; resolving." --json

echo "oracle: resolved PAYMENTS-501 in fix release and posted root-cause comment"

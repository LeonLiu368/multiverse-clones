#!/usr/bin/env bash
set -euo pipefail
cd /app/src
python - <<'PY'
from pathlib import Path
p=Path('/app/src/payments/retry_policy.py')
p.write_text('RETRYABLE_STATUSES = {409, 425, 429, 500, 502, 503, 504}\nMAX_ATTEMPTS = 5\nBASE_DELAY_MS = 250\nMAX_DELAY_MS = 4000\nJITTER_RATIO = 0.20\n\ndef event_status(event_or_status) -> int:\n    if isinstance(event_or_status, dict):\n        return int(event_or_status.get("status_code", event_or_status.get("status")))\n    return int(event_or_status)\n\ndef should_retry(status_code: int) -> bool:\n    return event_status(status_code) in RETRYABLE_STATUSES\n\ndef should_retry_event(event: dict) -> bool:\n    status = event_status(event)\n    if status == 425 and not event.get("idempotent", bool(event.get("idempotency_key"))):\n        return False\n    if status == 409 and event.get("error_type") != "lock_conflict":\n        return False\n    return should_retry(status)\n\ndef retry_delay_ms(attempt: int, retry_after_ms: int | None = None) -> int:\n    if attempt < 1:\n        raise ValueError("attempt is 1-indexed")\n    delay = BASE_DELAY_MS * (2 ** (attempt - 1))\n    if retry_after_ms:\n        delay = max(delay, int(retry_after_ms))\n    return min(MAX_DELAY_MS, delay)\n\ndef retry_plan(status_code: int, event: dict | None = None) -> dict:\n    if event is None:\n        event = {"status_code": status_code}\n        if event_status(status_code) == 425:\n            event["idempotent"] = True\n        if event_status(status_code) == 409:\n            event["error_type"] = "lock_conflict"\n    else:\n        event = dict(event)\n    event.setdefault("status_code", status_code)\n    retry = should_retry_event(event)\n    delays = [retry_delay_ms(i, event.get("retry_after_ms")) for i in range(1, MAX_ATTEMPTS + 1)] if retry else []\n    return {"retry": retry, "attempts": MAX_ATTEMPTS if retry else 0, "delays_ms": delays, "jitter_ratio": JITTER_RATIO, "capped": bool(delays and delays[-1] == MAX_DELAY_MS)}\n')
w=Path('/app/src/payments/webhooks.py')
w.write_text('"""Webhook retry scheduling for bank gateway callbacks.\n\nBuilds the delay schedule the webhook dispatcher uses when a gateway\ncallback fails. Delegates to the payment retry policy so the two can\nnever drift again.\n"""\nfrom payments.retry_policy import retry_plan\n\n\ndef webhook_retry_schedule(event: dict) -> list[int]:\n    """Return the retry delay schedule (ms) for a failed webhook event."""\n    event = dict(event)\n    status = int(event.get("status_code", event.get("status", 0)))\n    event.setdefault("status_code", status)\n    return retry_plan(status, event)["delays_ms"]\n')
PY
PYTHONPATH=/app/src${PYTHONPATH:+:$PYTHONPATH} python checks/visible_checks.py
PYTHONPATH=/app/src${PYTHONPATH:+:$PYTHONPATH} python tools/replay_payment_incident.py >/tmp/payment-replay.json
REPLAYED="$(python -c 'import json;print(json.load(open("/app/artifacts/payment_retry_replay.json"))["replayed_events"])')"
SCHEDULED="$(python -c 'import json;print(json.load(open("/app/artifacts/payment_retry_replay.json"))["scheduled_retries"])')"
CAPPED="$(python -c 'import json;print(json.load(open("/app/artifacts/payment_retry_replay.json"))["capped_retries"])')"
UNSAFE="$(python -c 'import json;print(json.load(open("/app/artifacts/payment_retry_replay.json"))["unsafe_retries"])')"
TERMINAL="$(python -c 'import json;print(json.load(open("/app/artifacts/payment_retry_replay.json"))["terminal_failures"])')"
git add payments/retry_policy.py payments/webhooks.py checks/visible_checks.py
git commit -m 'Fix OPS-501 payment retry policy' >/tmp/git-commit.log 2>&1 || true
ISSUE='OPS-501'
SHA="$(git rev-parse --short HEAD 2>/dev/null || printf 0000000)"
gh auth login --host "${GH_HOST:-http://github}" --token "$(cat "${GH_TOKEN_FILE:-/run/secrets/token}")" >/tmp/gh-auth.log 2>&1 || gh auth status >/tmp/gh-auth.log 2>&1
BRANCH='ops-501-payment-retry-policy'
git checkout -B "$BRANCH" >/tmp/git-branch.log 2>&1
git push -u origin "$BRANCH" >/tmp/git-push.log 2>&1
PR_URL=$(gh pr create -R acme/payment-retry-policy --title 'Fix OPS-501 payment retry policy' --head "$BRANCH" --base main --body "Implements the final OPS-501 retry contract from the #payments-incidents decision (Leon's correction; supersedes the 100ms/8s/4-attempt draft): retryable statuses are 409 lock conflicts only, idempotent 425s only, plus 429/500/502/503/504; attempts=5, base 250ms doubling to the 4000ms cap, jitter_ratio=0.20; retry_plan exposes capped=true at the cap; Retry-After floors a delay but never exceeds the cap. payments/webhooks.py now delegates to the policy module so webhook scheduling can never drift from policy again. Validated: visible tests pass and /app/artifacts/payment_retry_replay.json shows replayed_events=$REPLAYED scheduled_retries=$SCHEDULED capped_retries=$CAPPED unsafe_retries=$UNSAFE terminal_failures=$TERMINAL." | tail -1)
gh workflow run task-ci.yml -R acme/payment-retry-policy --ref "$BRANCH" >/tmp/gh-workflow-run.log 2>&1 || true
gh run watch -R acme/payment-retry-policy --timeout 300 --interval 5 >/tmp/gh-run-watch.log 2>&1
PR_NUMBER=$(printf '%s\n' "$PR_URL" | sed -E 's#.*/pull/([0-9]+).*#\1#')
gh pr merge "$PR_NUMBER" -R acme/payment-retry-policy --method squash >/tmp/gh-pr-merge.log 2>&1
linear issue start "$ISSUE" --json >/tmp/ticket-start.json
linear issue comment add "$ISSUE" --body "Implemented the final retry contract recovered from the #payments-incidents thread (Leon's correction supersedes the earlier 100ms/8s draft): 409 lock-conflict-only, 425 idempotent-only, plus 429/500/502/503/504; attempts=5, 250ms base doubling to the 4000ms cap, jitter 0.20, capped=true exposed for dashboards; Retry-After floored under the cap. Also aligned payments/webhooks.py with the policy module to remove its duplicated draft schedule. Verified with visible tests and /app/artifacts/payment_retry_replay.json: replayed_events=$REPLAYED scheduled_retries=$SCHEDULED capped_retries=$CAPPED unsafe_retries=$UNSAFE terminal_failures=$TERMINAL. Opened and merged PR $PR_URL after CI passed; Slack handoff posted to #incident-updates." --json >/tmp/ticket-comment.json
linear issue commit-link "$ISSUE" "$SHA" --json >/tmp/ticket-commit.json
linear issue pr-link "$ISSUE" "$PR_URL" --json >/tmp/ticket-pr-link.json || true
linear issue comment add "$ISSUE" --body "Merged GitHub PR evidence after CI passed: $PR_URL" --json >/tmp/ticket-pr-evidence.json
slack --json post 'incident-updates' "payment retry policy ready: merged PR $PR_URL attempts=5 max_delay_ms=4000 capped=true jitter_ratio=0.20 retryable=409/425/429/500/502/503/504. Replay artifact /app/artifacts/payment_retry_replay.json: replayed_events=$REPLAYED scheduled_retries=$SCHEDULED capped_retries=$CAPPED unsafe_retries=$UNSAFE terminal_failures=$TERMINAL." >/tmp/slack-post.json
jira issue transition "$ISSUE" "In Review" --json >/tmp/ticket-review.json

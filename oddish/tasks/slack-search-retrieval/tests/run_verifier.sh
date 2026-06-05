#!/bin/bash
# Deterministic verification: read #ask-platform back via the Slack API and confirm a
# message was posted there naming the CURRENT staging Postgres host:port
# (pg-staging.globex.internal:6432) — not the decommissioned/demo decoys.
# reward = 1 iff such a message exists, else 0. (nop -> 0, oracle -> 1.)
set -uo pipefail
mkdir -p /logs/verifier
API="${SLACK_API_URL:-http://slack:3000}"

resp="$(curl -sf "$API/api/conversations.history" --data-urlencode 'channel=ask-platform' --data-urlencode 'limit=100' || echo '{}')"

reward="$(python3 - "$resp" <<'PY'
import json, sys
TARGET = "pg-staging.globex.internal:6432"
LEGACY = "pg-staging-legacy.globex.internal"
try:
    d = json.loads(sys.argv[1])
    msgs = d.get("messages", [])
    ok = any(
        TARGET in m.get("text", "") and LEGACY not in m.get("text", "")
        for m in msgs
    )
    print(1 if ok else 0)
except Exception:
    print(0)
PY
)"

echo "$reward" > /logs/verifier/reward.txt
echo "reward=$reward"
exit 0

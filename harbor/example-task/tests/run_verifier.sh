#!/bin/bash
# Deterministic verification: read workspace state back via the Slack API and confirm
# a `ROOT CAUSE:` summary naming the connection-pool cause was posted to #incidents.
# reward = 1 iff such a message exists, else 0. (nop -> 0, oracle -> 1.)
set -uo pipefail
mkdir -p /logs/verifier
API="${SLACK_API_URL:-http://slack:3000}"

resp="$(curl -sf "$API/api/search.messages" --data-urlencode 'query=root cause in:#incidents' || echo '{}')"

reward="$(python3 - "$resp" <<'PY'
import json, sys
try:
    d = json.loads(sys.argv[1])
    matches = d.get("messages", {}).get("matches", [])
    ok = any(
        "root cause" in m.get("text", "").lower() and "connection pool" in m.get("text", "").lower()
        for m in matches
    )
    print(1 if ok else 0)
except Exception:
    print(0)
PY
)"

echo "$reward" > /logs/verifier/reward.txt
echo "reward=$reward"
exit 0

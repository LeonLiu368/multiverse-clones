#!/bin/bash
# Deterministic verification: read #design-decisions back via the Slack API and confirm a
# newly-authored decision summary was BOTH posted and PINNED, naming the chosen library.
# reward = 1 iff a pinned top-level message exists whose text mentions the decision and
# react-aria, else 0. (nop -> 0, oracle -> 1.)
#
# Discrimination: seed messages mention react-aria but none are pinned and none say
# "decision", so only a freshly posted-and-pinned summary satisfies all three.
set -uo pipefail
mkdir -p /logs/verifier
API="${SLACK_API_URL:-http://slack:3000}"

resp="$(curl -sf "$API/api/conversations.history" --data-urlencode 'channel=design-decisions' --data-urlencode 'limit=100' || echo '{}')"

reward="$(python3 - "$resp" <<'PY'
import json, sys
try:
    d = json.loads(sys.argv[1])
    msgs = d.get("messages", [])
    ok = any(
        m.get("pinned_to")
        and "react-aria" in m.get("text", "").lower()
        and "decision" in m.get("text", "").lower()
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

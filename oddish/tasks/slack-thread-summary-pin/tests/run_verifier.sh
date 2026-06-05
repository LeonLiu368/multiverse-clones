#!/bin/bash
# Deterministic verification (reads workspace state back via the Slack API).
# The agent succeeds iff the team's decision (adopt react-aria) is now captured as
# a NEW, PINNED message in #design-decisions. We key on the substance (a pinned
# message naming the chosen library), not exact wording.
#
# "NEW" = ts after the seed era (seed messages all have ts <= 1700000300), so
# merely pinning the pre-existing thread message that mentions react-aria is NOT
# enough — the agent must write the conclusion down and pin that. Uses
# search.messages so a pinned summary counts whether it's top-level or in-thread.
set -uo pipefail
mkdir -p /logs/verifier
API="${SLACK_API_URL:-http://slack:3000}"

resp="$(curl -sf "$API/api/search.messages" --data-urlencode 'query=react-aria in:#design-decisions' || echo '{}')"

reward="$(python3 - "$resp" <<'PY'
import json, sys
SEED_CUTOFF = 1700001000.0
try:
    d = json.loads(sys.argv[1])
    matches = d.get("messages", {}).get("matches", [])
    ok = False
    for m in matches:
        try:
            ts = float(m.get("ts", "0"))
        except ValueError:
            continue
        if ts > SEED_CUTOFF and m.get("pinned_to") and "react-aria" in m.get("text", "").lower():
            ok = True
            break
    print(1 if ok else 0)
except Exception:
    print(0)
PY
)"

echo "$reward" > /logs/verifier/reward.txt
echo "reward=$reward"
exit 0

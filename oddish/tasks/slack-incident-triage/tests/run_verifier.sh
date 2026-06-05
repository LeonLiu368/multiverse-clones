#!/bin/bash
# Deterministic verification (reads workspace state back via the Slack API).
# The agent succeeds iff it posted a NEW message in #incidents that names the
# underlying cause of the outage — the DB connection pool being exhausted by the
# v2.3 concurrency bump. We key on the substance, not any exact wording, so a
# genuine writeup passes regardless of phrasing.
#
# "NEW" = ts after the seed era (seed messages all have ts <= 1700000300; a real
# post gets a current-epoch ts ~1.7e9+). This excludes the seeded thread reply
# that already mentions the connection pool. reward=1 iff such a message exists.
set -uo pipefail
mkdir -p /logs/verifier
API="${SLACK_API_URL:-http://slack:3000}"

resp="$(curl -sf "$API/api/search.messages" --data-urlencode 'query=connection pool in:#incidents' || echo '{}')"

reward="$(python3 - "$resp" <<'PY'
import json, sys
SEED_CUTOFF = 1700001000.0
CAUSE_HINTS = ("exhaust", "concurrency", "pool size", "capacity", "saturat", "ran out", "too small")
try:
    d = json.loads(sys.argv[1])
    matches = d.get("messages", {}).get("matches", [])
    ok = False
    for m in matches:
        try:
            ts = float(m.get("ts", "0"))
        except ValueError:
            continue
        text = m.get("text", "").lower()
        if ts > SEED_CUTOFF and "connection pool" in text and any(h in text for h in CAUSE_HINTS):
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

#!/bin/bash
# Deterministic verification (reads workspace state back via the Slack API).
# The agent succeeds iff it answered in #ask-platform with the CURRENT staging
# Postgres host:port — `pg-staging.globex.internal:6432`. That exact string is
# the answer; the decommissioned host is a different name (pg-staging-legacy...)
# on a different port (:5432), so requiring the exact current value already
# excludes the decoys. (An answer may also mention the old host as a warning.)
#
# Uses search.messages so the answer is found whether posted top-level or as a
# reply to the question. reward=1 iff such a message exists.
set -uo pipefail
mkdir -p /logs/verifier
API="${SLACK_API_URL:-http://slack:3000}"

resp="$(curl -sf "$API/api/search.messages" --data-urlencode 'query=pg-staging in:#ask-platform' || echo '{}')"

reward="$(python3 - "$resp" <<'PY'
import json, sys
TARGET = "pg-staging.globex.internal:6432"
try:
    d = json.loads(sys.argv[1])
    matches = d.get("messages", {}).get("matches", [])
    ok = any(TARGET in m.get("text", "") for m in matches)
    print(1 if ok else 0)
except Exception:
    print(0)
PY
)"

echo "$reward" > /logs/verifier/reward.txt
echo "reward=$reward"
exit 0

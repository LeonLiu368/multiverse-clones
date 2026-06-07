#!/bin/bash
# Deterministic verification (runs in the client container). reward = 1 iff BOTH:
#   (A) CODE: the candidate's monitoring package passes the full TRUSTED suite, including the
#       HIDDEN paging-policy grading test; AND
#   (B) COMMUNICATION: a message was posted to #postmortems that states the root cause and the
#       sustained/consecutive-breach fix (the "action beyond coding").
# else 0. (nop -> 0, oracle -> 1.)
set -uo pipefail
mkdir -p /logs/verifier
TRUSTED="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/trusted"

# ---- (A) code grade, in a fresh verifier-owned dir (ignores agent edits to /workspace/tests)
GRADE="/tmp/grade.$$"
rm -rf "$GRADE"; mkdir -p "$GRADE"
cp -r /workspace/monitoring "$GRADE/monitoring"
cp "$TRUSTED"/test_window.py "$TRUSTED"/test_alerts.py "$TRUSTED"/test_grade_alerts.py "$GRADE/"
code_ok=0
if ( cd "$GRADE" && python -m pytest -q -p no:cacheprovider ) >/logs/verifier/pytest.log 2>&1; then
  code_ok=1
fi
rm -rf "$GRADE"

# ---- (B) communication check, via the Slack Web API (the same gateway the agent uses; the
# Mattermost backend is not reachable from here). reward requires a #postmortems message that
# names the root cause and the sustained/consecutive-breach fix.
BASE="${SLACK_API_URL:-http://api}"; TOK="${SLACK_BOT_TOKEN:-xoxb-acme-eval-0001}"
comm_ok=0
hits="$(curl -sS "$BASE/api/conversations.history?channel=postmortems&limit=200" \
  -H "Authorization: Bearer $TOK" \
  | jq '[.messages[]? | select((.text|ascii_downcase|contains("root cause"))
         and ((.text|ascii_downcase|contains("consecutive")) or (.text|ascii_downcase|contains("sustained"))))] | length' 2>/dev/null)"
[ "${hits:-0}" -ge 1 ] && comm_ok=1

echo "code_ok=$code_ok comm_ok=$comm_ok"
if [ "$code_ok" -eq 1 ] && [ "$comm_ok" -eq 1 ]; then
  echo "1" > /logs/verifier/reward.txt
  echo "reward=1 (fix passes hidden policy grading AND postmortem posted to #postmortems)"
else
  echo "0" > /logs/verifier/reward.txt
  echo "reward=0 (code_ok=$code_ok, comm_ok=$comm_ok)"
  [ "$code_ok" -ne 1 ] && tail -20 /logs/verifier/pytest.log
fi
exit 0

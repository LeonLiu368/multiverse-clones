#!/bin/bash
# reward=1 iff BOTH: (A) candidate budget/ passes trusted suite + hidden grader, AND
# (B) a message was posted to #error-budget-reports referencing the error_rate and budget thresholds.
set -uo pipefail
mkdir -p /logs/verifier
TRUSTED="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/trusted"

GRADE="/tmp/grade.$$"
rm -rf "$GRADE"; mkdir -p "$GRADE"
cp -r /workspace/budget "$GRADE/budget"
cp "$TRUSTED"/test_monitor.py "$TRUSTED"/test_window.py "$TRUSTED"/test_grade_monitor.py "$GRADE/"

code_ok=0
if ( cd "$GRADE" && python3 -m pytest -q -p no:cacheprovider ) >/logs/verifier/pytest.log 2>&1; then
  code_ok=1
fi
rm -rf "$GRADE"

BASE="${SLACK_API_URL:-http://localhost}"; TOK="${SLACK_BOT_TOKEN:-xoxp-acme-eval-0001}"
comm_ok=0
hits="$(curl -sS "$BASE/api/conversations.history?channel=error-budget-reports&limit=200" \
  -H "Authorization: Bearer $TOK" \
  | jq '[.messages[]? | (.text // "") | ascii_downcase
        | select(contains("error_rate") or contains("error rate"))
        | select(contains("budget"))
        | select(contains("0.05") or contains("threshold"))
       ] | length' 2>/dev/null)"
[ "${hits:-0}" -ge 1 ] && comm_ok=1

echo "code_ok=$code_ok comm_ok=$comm_ok"
if [ "$code_ok" -eq 1 ] && [ "$comm_ok" -eq 1 ]; then
  echo "1" > /logs/verifier/reward.txt
  echo "reward=1 (fix passes hidden grading AND notification posted to #error-budget-reports)"
else
  echo "0" > /logs/verifier/reward.txt
  echo "reward=0 (code_ok=$code_ok, comm_ok=$comm_ok)"
  [ "$code_ok" -ne 1 ] && tail -20 /logs/verifier/pytest.log
fi
exit 0

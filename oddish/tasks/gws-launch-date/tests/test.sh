#!/usr/bin/env bash
# Verifier for gws-launch-date. reward=1 iff the candidate launch package passes the
# visible invariant tests AND the HIDDEN grader (the date recovered from the Google
# Doc), graded in a fresh verifier-owned dir.
set -uo pipefail
mkdir -p /logs/verifier 2>/dev/null || true
HERE="$(cd "$(dirname "$0")" && pwd)"
GRADE="/tmp/grade.$$"; mkdir -p "$GRADE"
cp -r /app/launch "$GRADE/launch"
cp "$HERE/trusted/test_launch.py" "$HERE/trusted/test_grade_launch.py" "$GRADE/"
code_ok=0
( cd "$GRADE" && python3 -m pytest -q ) > /logs/verifier/pytest.log 2>&1 && code_ok=1
echo "[verifier] code_ok=$code_ok"; tail -n 2 /logs/verifier/pytest.log 2>/dev/null || true
reward=0; [ "$code_ok" = 1 ] && reward=1
echo "$reward" > /logs/verifier/reward.txt 2>/dev/null || true
echo "reward=$reward"; exit 0

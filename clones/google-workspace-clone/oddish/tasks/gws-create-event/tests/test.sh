#!/usr/bin/env bash
# Verifier for gws-create-event. reward=1 iff the agent CREATED the confirmed
# 'Q3 Retro' event — checked by reading the calendar back THROUGH THE API (write->read
# round-trip, R5.2). Graded in a fresh verifier-owned dir.
set -uo pipefail
mkdir -p /logs/verifier 2>/dev/null || true
HERE="$(cd "$(dirname "$0")" && pwd)"
GRADE="/tmp/grade.$$"; mkdir -p "$GRADE"
cp "$HERE/trusted/test_grade_event.py" "$GRADE/"
code_ok=0
( cd "$GRADE" && python3 -m pytest -q ) > /logs/verifier/pytest.log 2>&1 && code_ok=1
echo "[verifier] code_ok=$code_ok"; tail -n 3 /logs/verifier/pytest.log 2>/dev/null || true
reward=0; [ "$code_ok" = 1 ] && reward=1
echo "$reward" > /logs/verifier/reward.txt 2>/dev/null || true
echo "reward=$reward"; exit 0

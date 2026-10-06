#!/usr/bin/env bash
set -uo pipefail
mkdir -p /logs/verifier 2>/dev/null || true
HERE="$(cd "$(dirname "$0")" && pwd)"
GRADE="/tmp/grade.$$"; mkdir -p "$GRADE"
cp -r /app/ios_components "$GRADE/ios_components"
cp "$HERE/trusted/test_comp.py" "$HERE/trusted/test_grade_comp.py" "$GRADE/"
code_ok=0
( cd "$GRADE" && python3 -m pytest -q ) > /logs/verifier/pytest.log 2>&1 && code_ok=1
echo "[verifier] code_ok=$code_ok"; tail -n 2 /logs/verifier/pytest.log 2>/dev/null || true
reward=0; [ "$code_ok" = 1 ] && reward=1
echo "$reward" > /logs/verifier/reward.txt 2>/dev/null || true
echo "reward=$reward"; exit 0

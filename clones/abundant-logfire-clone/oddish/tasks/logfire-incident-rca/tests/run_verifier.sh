#!/bin/bash
# Deterministic verification for logfire-incident-rca.
#
# reward=1 iff the candidate code (the agent's edited /workspace) passes BOTH the visible
# invariant tests AND the HIDDEN grader, which pins the EXACT root cause recovered from the
# production telemetry (oddish-worker / asyncpg.exceptions.UndefinedColumnError /
# queue_slots.locked_at / 60 occurrences) plus the schema fix.
#
# Grading runs in a fresh verifier-owned dir (NOT /workspace) so the agent can't pre-place
# a passing tests/ tree. The grader's trusted tests come from THIS dir, not the agent's.
set -uo pipefail
mkdir -p /logs/verifier
HERE="$(cd "$(dirname "$0")" && pwd)"

GRADE="/tmp/grade.$$"
mkdir -p "$GRADE"
# candidate code under test
cp -r /workspace/queue "$GRADE/queue"
cp /workspace/incident_rca.py "$GRADE/incident_rca.py"
# trusted tests (visible shape check + hidden exact-value grader)
cp "$HERE/trusted/test_grade_rca.py" "$GRADE/test_grade_rca.py"

reward=0
# ensure pytest (thin pulled agent may not ship it)
python3 -c "import pytest" 2>/dev/null || python3 -m pip install -q --disable-pip-version-check pytest >/dev/null 2>&1 || true
( cd "$GRADE" && PYTHONPATH="$GRADE" python3 -m pytest -q test_grade_rca.py ) \
  > /logs/verifier/pytest.log 2>&1 && reward=1
echo "[verifier] reward=$reward"
tail -n 8 /logs/verifier/pytest.log

echo "$reward" > /logs/verifier/reward.txt
echo "reward=$reward"
exit 0

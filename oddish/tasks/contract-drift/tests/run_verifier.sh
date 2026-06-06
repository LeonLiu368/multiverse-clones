#!/bin/bash
# Deterministic verification (runs in the client container).
# reward = 1 iff the candidate's payments package passes the full TRUSTED suite — the
# canonical serialization/charge invariant tests plus the HIDDEN v2-contract grading test —
# else 0. (nop -> 0, oracle -> 1.)
#
# Trust boundary: grade in a fresh verifier-owned dir, copying in the candidate's `payments/`
# package + the TRUSTED test files. The agent's /workspace/tests is never executed, and the
# hidden grading test is absent from the agent's container during the run.
set -uo pipefail
mkdir -p /logs/verifier
TRUSTED="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/trusted"

GRADE="/tmp/grade.$$"
rm -rf "$GRADE"; mkdir -p "$GRADE"
cp -r /workspace/payments "$GRADE/payments"
cp "$TRUSTED"/test_serialization.py "$TRUSTED"/test_charge.py "$TRUSTED"/test_grade_charge.py "$GRADE/"

cd "$GRADE"
if python -m pytest -q -p no:cacheprovider >/logs/verifier/pytest.log 2>&1; then
  echo "1" > /logs/verifier/reward.txt
  echo "reward=1 (candidate payments passes the trusted suite, including hidden v2-contract grading)"
else
  echo "0" > /logs/verifier/reward.txt
  echo "reward=0 (trusted suite failing)"
  tail -25 /logs/verifier/pytest.log
fi
rm -rf "$GRADE"
exit 0

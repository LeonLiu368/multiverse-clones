#!/bin/bash
# Deterministic verification (runs in the client container).
# reward = 1 iff the candidate's billing package passes the full TRUSTED suite — the
# canonical money/fees invariant tests plus the HIDDEN policy-grading test — else 0.
# (nop -> 0, oracle -> 1.)
#
# Trust boundary: we grade in a fresh verifier-owned directory, copying in the candidate's
# `billing/` package under test and the TRUSTED test files. We never run the agent's own
# /workspace/tests, so the agent cannot pass by weakening/deleting/replacing tests, and the
# hidden grading test (which encodes the policy) is never present in the agent's container
# during the run — only here, at grading time.
set -uo pipefail
mkdir -p /logs/verifier
TRUSTED="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/trusted"

GRADE="/tmp/grade.$$"
rm -rf "$GRADE"; mkdir -p "$GRADE"
cp -r /workspace/billing "$GRADE/billing"                 # candidate code under test
cp "$TRUSTED"/test_money.py "$TRUSTED"/test_fees.py "$TRUSTED"/test_grade_fees.py "$GRADE/"

cd "$GRADE"
if python -m pytest -q -p no:cacheprovider >/logs/verifier/pytest.log 2>&1; then
  echo "1" > /logs/verifier/reward.txt
  echo "reward=1 (candidate billing passes the trusted suite, including hidden policy grading)"
else
  echo "0" > /logs/verifier/reward.txt
  echo "reward=0 (trusted suite failing)"
  tail -25 /logs/verifier/pytest.log
fi
rm -rf "$GRADE"
exit 0

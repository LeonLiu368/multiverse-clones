#!/bin/bash
# Deterministic verification: apply the hidden regression test (test.patch) and run it.
# reward=1 iff the F2P Go test passes.
set -uo pipefail
mkdir -p /logs/verifier
cd /app/repo || { echo 0 > /logs/verifier/reward.txt; exit 0; }
git config --global --add safe.directory /app/repo 2>/dev/null || true

git apply /tests/test.patch 2>/logs/verifier/patch.err || patch -p1 < /tests/test.patch 2>>/logs/verifier/patch.err || {
  echo "failed to apply test.patch" >> /logs/verifier/patch.err
  echo 0 > /logs/verifier/reward.txt
  exit 0
}

LOG=/logs/verifier/test-output.txt
set +e
go test ./eth/ -run 'TestRequestClose|TestDoWitnessRequest_CancelPaths|TestRequestWitnesses_LeakFixes' -count=1 -timeout 180s >"$LOG" 2>&1
RC=$?
set -e
tail -20 "$LOG" || true

if [ "$RC" -eq 0 ]; then echo 1 > /logs/verifier/reward.txt; else echo 0 > /logs/verifier/reward.txt; fi
echo "reward=$(cat /logs/verifier/reward.txt)"
exit 0

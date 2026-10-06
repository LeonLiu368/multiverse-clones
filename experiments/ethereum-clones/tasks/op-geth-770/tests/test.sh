#!/usr/bin/env bash
set -euo pipefail
mkdir -p /logs/verifier
rm -f /logs/verifier/reward.txt /logs/verifier/reward.json /logs/verifier/test.log

if /tests/stage_data.sh >> /logs/verifier/test.log 2>&1 &&    /tests/run_candidate.sh >> /logs/verifier/test.log 2>&1 &&    /tests/run_verifier.sh >> /logs/verifier/test.log 2>&1 &&    python3 /tests/check_ticket_state.py >> /logs/verifier/test.log 2>&1; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi

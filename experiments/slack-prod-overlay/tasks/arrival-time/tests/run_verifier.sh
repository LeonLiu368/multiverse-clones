#!/bin/bash
# reward=1 iff /workspace/answer.txt reports the planted arrival time (18:00). The planted
# #engineering message says the teammate is "coming in at 6pm" to push the payments hotfix.
set -uo pipefail
mkdir -p /logs/verifier
TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if python3 "$TESTS_DIR/verify.py"; then
  echo "1" > /logs/verifier/reward.txt
else
  echo "0" > /logs/verifier/reward.txt
fi
echo "reward=$(cat /logs/verifier/reward.txt)"

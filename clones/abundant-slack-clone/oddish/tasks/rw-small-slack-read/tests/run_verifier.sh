#!/bin/bash
# reward=1 iff /workspace/answer.txt reports the correct count of messages containing "testing".
# Ground truth for this tiny export: exactly 2 messages contain "testing".
set -uo pipefail
mkdir -p /logs/verifier
EXPECTED=2

ans="$(grep -oE '[0-9]+' /workspace/answer.txt 2>/dev/null | head -1)"
if [ "${ans:-}" = "$EXPECTED" ]; then
  echo "1" > /logs/verifier/reward.txt
  echo "reward=1 (answer=$ans)"
else
  echo "0" > /logs/verifier/reward.txt
  echo "reward=0 (answer=${ans:-<none>}, expected=$EXPECTED)"
fi
exit 0

#!/bin/bash
# reward=1 iff /workspace/answers.txt has all three correct values for the full export:
#   channels=88   tsr_messages=54   tsr_survey=4   (#testing-survey-responses, via conversations.history)
set -uo pipefail
mkdir -p /logs/verifier
declare -A EXPECTED=( [channels]=88 [tsr_messages]=54 [tsr_survey]=4 )
val() { grep -oE "^$1=[0-9]+" /workspace/answers.txt 2>/dev/null | head -1 | grep -oE '[0-9]+'; }
ok=1; report=""
for k in "${!EXPECTED[@]}"; do
  got="$(val "$k")"; report+="$k=${got:-<none>}(want ${EXPECTED[$k]}) "
  [ "${got:-}" = "${EXPECTED[$k]}" ] || ok=0
done
if [ "$ok" -eq 1 ]; then echo "1" > /logs/verifier/reward.txt; echo "reward=1 ($report)"
else echo "0" > /logs/verifier/reward.txt; echo "reward=0 ($report)"; fi
exit 0

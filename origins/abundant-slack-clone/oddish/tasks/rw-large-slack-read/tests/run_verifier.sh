#!/bin/bash
# reward=1 iff /workspace/answers.txt reports all three correct values for this committed slice:
#   deploys_deploy=69   (70 top-level msgs in #deploys; "deploy" substring; channel has no threads)
#   product_release=32  ("release" in #product history / top-level messages)
#   channels=4          (deploys, engineering, growthsquad, product)
set -uo pipefail
mkdir -p /logs/verifier
declare -A EXPECTED=( [deploys_deploy]=69 [product_release]=32 [channels]=4 )

val() { grep -oE "^$1=[0-9]+" /workspace/answers.txt 2>/dev/null | head -1 | grep -oE '[0-9]+'; }

ok=1; report=""
for k in "${!EXPECTED[@]}"; do
  got="$(val "$k")"
  report+="$k=${got:-<none>}(want ${EXPECTED[$k]}) "
  [ "${got:-}" = "${EXPECTED[$k]}" ] || ok=0
done

if [ "$ok" -eq 1 ]; then
  echo "1" > /logs/verifier/reward.txt
  echo "reward=1 ($report)"
else
  echo "0" > /logs/verifier/reward.txt
  echo "reward=0 ($report)"
fi
exit 0

#!/bin/bash
# Local validation of figma-spec-recovery WITHOUT the Harbor runner.
#
# Mirrors what Harbor does: build the agent (`main`) image, run the prebuilt
# `figma` service with this task's fixture.json mounted into the SERVICE only,
# then check the reward for three scenarios:
#   nop    → 0   (no code change, no comment)
#   oracle → 1   (solution/solve.sh)
#   decoy  → 0   (plausible-but-wrong v1 values, even with a comment posted)
#
# Requires the figma-service image. Build it first from the repo root:
#   docker build -f docker/Dockerfile -t ghcr.io/leonliu368/figma-service:latest .
set -uo pipefail
cd "$(dirname "$0")"
TASK_DIR="$(pwd)"
NET=figmaval$$
IMG_SVC=ghcr.io/leonliu368/figma-service:latest
IMG_AGENT=figma-agent-local:$$
KEY=Pr1cingCardSpecFile001

cleanup() { docker rm -f figma main >/dev/null 2>&1; docker network rm "$NET" >/dev/null 2>&1; }
trap cleanup EXIT

echo "### building agent image"
docker build -q -t "$IMG_AGENT" "$TASK_DIR/environment" >/dev/null

run_scenario() {  # $1 = name, $2 = setup-cmd (run inside main before verifier)
  local name="$1" setup="$2"
  docker rm -f figma main >/dev/null 2>&1
  docker network create "$NET" >/dev/null 2>&1 || true
  docker run -d --name figma --network "$NET" --network-alias figma \
    -e FIGMA_FIXTURE=/srv/fixture.json \
    -v "$TASK_DIR/environment/fixture.json:/srv/fixture.json:ro" "$IMG_SVC" >/dev/null
  # wait for health
  for i in $(seq 1 30); do
    docker exec figma python -c "import urllib.request;urllib.request.urlopen('http://localhost:3000/health')" >/dev/null 2>&1 && break
    sleep 1
  done
  docker run -d --name main --network "$NET" \
    -e FIGMA_API_URL=http://figma:3000 -e FIGMA_TOKEN=figma-clone-token -e FIGMA_FILE_KEY=$KEY \
    "$IMG_AGENT" sleep infinity >/dev/null
  docker cp "$TASK_DIR/tests" main:/verifier >/dev/null
  docker cp "$TASK_DIR/solution/solve.sh" main:/solve.sh >/dev/null
  [ -n "$setup" ] && docker exec main bash -lc "$setup" >/dev/null 2>&1
  docker exec main bash /verifier/run_verifier.sh >/dev/null 2>&1
  local reward
  reward=$(docker exec main cat /logs/verifier/reward.txt 2>/dev/null || echo "ERR")
  printf "  %-7s reward=%s\n" "$name" "$reward"
  echo "$reward"
}

echo "### scenarios"
nop=$(run_scenario "nop" "" | tail -1)
oracle=$(run_scenario "oracle" "bash /solve.sh" | tail -1)
decoy_setup='python3 - <<PY
import re,io
p="/workspace/pricing_card/card.py"
open(p,"w").write("""def pricing_card_style():
    return {"heading":"Pro","price":"\$29/mo","card_padding":16,"card_gap":12,"card_radius":8,"cta_label":"Sign up","cta_color":"#1D4ED8","cta_radius":8}
""")
PY
figma-cli comments add '"$KEY"' --node 1:2 -m "done (decoy)"'
decoy=$(run_scenario "decoy" "$decoy_setup" | tail -1)

echo "### result"
if [ "$nop" = "0" ] && [ "$oracle" = "1" ] && [ "$decoy" = "0" ]; then
  echo "PASS ✓  nop=0 oracle=1 decoy=0"; exit 0
else
  echo "FAIL ✗  nop=$nop oracle=$oracle decoy=$decoy"; exit 1
fi

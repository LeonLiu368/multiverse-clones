#!/bin/bash
# Local validation of gauge-annotation-roundtrip WITHOUT the Harbor runner.
#
# Mirrors what Harbor does: build the thin agent (`main`) image, run the `gauge` gateway
# with this task's fixture.json mounted into the SERVICE only, then check the reward for:
#   nop    → 0   (no annotation posted)
#   oracle → 1   (solution/solve.sh)
#   decoy  → 0   (an annotation IS posted, but missing the root-cause keyword)
#
# Also asserts agent isolation: no seed on disk, `gaugectl` absent, and the gateway's
# seed/state source is not importable in the agent (the R2.k leak probe).
set -uo pipefail
cd "$(dirname "$0")"
TASK_DIR="$(pwd)"
NET=gaugeval$$
IMG_SVC=ghcr.io/abundant-ai/gauge-service:tasklocal
IMG_AGENT=gauge-agent-local:$$

cleanup() { docker rm -f gauge main >/dev/null 2>&1; docker network rm "$NET" >/dev/null 2>&1; }
trap cleanup EXIT

echo "### building gauge gateway image (from the vendored gauge.Dockerfile — no registry pull)"
docker build -q -t "$IMG_SVC" -f "$TASK_DIR/environment/gauge.Dockerfile" "$TASK_DIR/environment" >/dev/null
echo "### building thin agent image"
docker build -q -t "$IMG_AGENT" "$TASK_DIR/environment" >/dev/null

start_stack() {
  docker rm -f gauge main >/dev/null 2>&1
  docker network create "$NET" >/dev/null 2>&1 || true
  docker run -d --name gauge --network "$NET" --network-alias gauge \
    -e GAUGE_STATE_FILE=/srv/gauge/fixture.json \
    -e GAUGE_RUNTIME_STATE_FILE=/var/lib/gauge/state.json \
    -v "$TASK_DIR/environment/fixture.json:/srv/gauge/fixture.json:ro" "$IMG_SVC" >/dev/null
  for i in $(seq 1 30); do
    docker exec gauge python -c "import urllib.request;urllib.request.urlopen('http://localhost/api/healthz')" >/dev/null 2>&1 && break
    sleep 1
  done
  docker run -d --name main --network "$NET" \
    -e GRAFANA_URL=http://gauge -e GRAFANA_TOKEN=test-token-acme-eval \
    "$IMG_AGENT" sleep infinity >/dev/null
  docker cp "$TASK_DIR/tests" main:/verifier >/dev/null
  docker cp "$TASK_DIR/solution/solve.sh" main:/solve.sh >/dev/null
}

run_scenario() {  # $1 = name, $2 = setup-cmd (run inside main before verifier)
  local name="$1" setup="$2"
  start_stack
  [ -n "$setup" ] && docker exec main bash -lc "$setup" >/dev/null 2>&1
  docker exec -e GRAFANA_URL=http://gauge main bash /verifier/run_verifier.sh >/dev/null 2>&1
  local reward
  reward=$(docker exec main cat /logs/verifier/reward.txt 2>/dev/null || echo "ERR")
  echo "$reward"
}

echo "### isolation probes (R2.k / R6.3)"
start_stack
iso_ok=1
docker exec main sh -c '[ ! -e /data/gauge/state.json ] && [ ! -e /srv/gauge/fixture.json ]' || { echo "  LEAK: seed file present"; iso_ok=0; }
docker exec main sh -lc '! command -v gaugectl' >/dev/null 2>&1 || { echo "  LEAK: gaugectl present"; iso_ok=0; }
docker exec main python -c 'import gauge.server.state' >/dev/null 2>&1 && { echo "  LEAK: gauge.server.state importable"; iso_ok=0; }
docker exec main sh -c 'test ! -e /opt/gaugecli/gauge/server/state.py' || { echo "  LEAK: server/state.py present"; iso_ok=0; }
docker exec main gcx dashboards search payment --json >/dev/null 2>&1 || { echo "  agent cannot reach gateway over HTTP"; iso_ok=0; }
[ "$iso_ok" = "1" ] && echo "  isolation OK (no seed, no gaugectl, state not importable, HTTP reachable)"

echo "### scenarios"
nop=$(run_scenario "nop" "")
oracle=$(run_scenario "oracle" "bash /solve.sh")
decoy=$(run_scenario "decoy" 'gcx annotations create --dashboard dash-payment-webhooks --panel 1 --text "looked at it, all fine" --tags incident --json')
printf "  nop    reward=%s\n  oracle reward=%s\n  decoy  reward=%s\n" "$nop" "$oracle" "$decoy"

echo "### result"
if [ "$nop" = "0" ] && [ "$oracle" = "1" ] && [ "$decoy" = "0" ] && [ "$iso_ok" = "1" ]; then
  echo "PASS  nop=0 oracle=1 decoy=0 isolation=ok"; exit 0
else
  echo "FAIL  nop=$nop oracle=$oracle decoy=$decoy isolation=$iso_ok"; exit 1
fi

#!/usr/bin/env bash
# Local validation of conduit-live-k8s WITHOUT the Harbor runner.
#
# Bakes the airgap images, brings the TWO-service compose up (k3s + main), waits
# for the in-cluster stack to come up, confirms live spans reach logfire, then:
#   - NOP:    faulty deployment (WEB_CONCURRENCY=1), no fix, no findings -> reward 0
#   - ORACLE: solution/solve.sh applies the fix + findings -> reward 1  (x3 stability)
#
# Env: KEEP=1 leaves the stack up. SKIP_BAKE=1 reuses existing airgap tars.
set -uo pipefail
cd "$(dirname "$0")"
TASK_DIR="$(pwd)"
PROJ=conduit-live-k8s
ENVDIR="$TASK_DIR/environment"
DC="docker compose -p $PROJ -f $ENVDIR/docker-compose.yaml"
MAIN="$PROJ-main-1"
K3S="$PROJ-k3s-1"

cleanup() { [ "${KEEP:-0}" = "1" ] && { echo "KEEP=1 — leaving stack up"; return; }
  $DC down -v --remove-orphans >/dev/null 2>&1
}
trap cleanup EXIT

kubectl_k3s() { docker exec "$K3S" kubectl -n conduit "$@"; }

query_logfire() {  # $1 = sql ; runs from inside main against the NodePort
  docker exec "$MAIN" sh -c "curl -s -X POST http://k3s:30080/v2/query \
    -H 'Authorization: Bearer task-read-token' -H 'Content-Type: application/json' \
    --data '{\"sql\":\"$1\",\"min_timestamp\":\"2026-07-01T00:00:00Z\"}'"
}

run_soak() {  # writes reward to stdout
  docker exec -e SOAK_TARGET=http://k3s:30800 \
              -e SOAK_CONFIG=/verifier/soak_config.json \
              -e REWARD_DIR=/logs/verifier \
              "$MAIN" bash /verifier/run_verifier.sh >/dev/null 2>&1
  docker exec "$MAIN" cat /logs/verifier/reward.txt 2>/dev/null
}

echo "### baking airgap images (build SUT + docker save the 4 workload images)"
[ "${SKIP_BAKE:-0}" = "1" ] || "$ENVDIR/k3s/bake-images.sh"

echo "### building + starting the two-service stack (k3s + main)"
$DC build >/dev/null
$DC up -d k3s >/dev/null
echo "### waiting for k3s healthy"
until docker exec "$K3S" kubectl get --raw=/readyz >/dev/null 2>&1; do sleep 3; done
echo "### waiting for in-cluster workloads (postgres, logfire, otel-collector, conduit)"
for d in postgres logfire otel-collector conduit; do
  echo -n "  waiting deploy/$d ... "
  docker exec "$K3S" kubectl -n conduit rollout status deploy/$d --timeout=300s >/dev/null 2>&1 \
    && echo "Ready" || echo "TIMEOUT (continuing)"
done
echo "### waiting for the seed Job to complete"
docker exec "$K3S" kubectl -n conduit wait --for=condition=complete job/conduit-seed --timeout=180s >/dev/null 2>&1 \
  && echo "  seed complete" || echo "  seed not complete (continuing)"

$DC up -d main >/dev/null
echo "### waiting for main entrypoint to see the environment ready"
sleep 5

echo "### drive a little load so spans exist, then confirm live spans in logfire"
docker exec "$MAIN" sh -c 'for i in $(seq 1 12); do curl -s -o /dev/null http://k3s:30800/api/articles; done'
sleep 3
N=$(query_logfire "SELECT count(*) c FROM records WHERE service_name = char(99,111,110,100,117,105,116)" | grep -o '"c": *[0-9]*' | grep -o '[0-9]*' | head -1)
echo "  live conduit spans in logfire: ${N:-0}"
[ "${N:-0}" -gt 0 ] && echo "  LIVE SPANS OK" || { echo "  FAIL: no conduit spans in logfire"; exit 1; }

echo "### install verifier into main"
docker cp "$TASK_DIR/tests" "$MAIN:/verifier" >/dev/null

echo "### NOP (faulty, no fix, no findings) -> expect reward 0"
docker exec "$MAIN" sh -c 'rm -f /workspace/findings.json' 2>/dev/null || true
NOP=$(run_soak); echo "  NOP reward = $NOP"

echo "### ORACLE x3 (solve.sh applies fix + findings) -> expect reward 1 each"
docker cp "$TASK_DIR/solution/solve.sh" "$MAIN:/solve.sh" >/dev/null
ORACLE_OK=1
for r in 1 2 3; do
  # re-arm the fault before each oracle run so it's a real fix each time
  kubectl_k3s set env deploy/conduit WEB_CONCURRENCY=1 >/dev/null 2>&1
  kubectl_k3s rollout status deploy/conduit --timeout=180s >/dev/null 2>&1
  until docker exec "$MAIN" curl -fsS -m3 http://k3s:30800/api/tags >/dev/null 2>&1; do sleep 2; done
  docker exec "$MAIN" sh -c 'rm -f /workspace/findings.json'
  docker exec "$MAIN" bash /solve.sh >/dev/null 2>&1
  OR=$(run_soak); echo "  ORACLE run $r reward = $OR"
  [ "$OR" = "1.0" ] || ORACLE_OK=0
done

echo "======================================================"
echo "  NOP=$NOP   ORACLE=(x3 above)   oracle_all_pass=$ORACLE_OK"
[ "$NOP" = "0.0" ] && [ "$ORACLE_OK" = "1" ] && echo "  VALIDATION PASS (nop=0, oracle=1 x3)" || echo "  VALIDATION FAIL"
echo "======================================================"

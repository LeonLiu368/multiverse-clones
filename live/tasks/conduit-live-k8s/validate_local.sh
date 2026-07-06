#!/usr/bin/env bash
# Local validation of conduit-live-k8s WITHOUT the Harbor runner.
#
# The manifests pull PUBLIC images at runtime (imagePullPolicy: IfNotPresent). The
# two abundant-ai images (logfire-service, conduit-otel) are not flipped public yet,
# so for a LOCAL run this script IMPORTS the workload images into k3s's containerd
# (k8s.io namespace) after boot — then IfNotPresent finds them without any registry
# pull. This writes nothing to the tree and is NOT part of the task Dockerfile.
# (On Oddish the flip makes k3s pull them itself; no import step needed there.)
#
# Then brings the TWO-service compose up (k3s + main), confirms live spans reach
# logfire, and:
#   - NOP:    faulty deployment (WEB_CONCURRENCY=1), no fix, no findings -> reward 0
#   - ORACLE: solution/solve.sh applies the fix + findings -> reward 1  (x3 stability)
#
# Env: KEEP=1 leaves the stack up.
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

# Count live conduit spans via the agent's own `logfire` CLI (the real read path),
# which reaches http://k3s:30080 with the read token from the main image's env.
count_conduit_spans() {
  docker exec "$MAIN" logfire query \
    "SELECT count(*) c FROM records WHERE service_name = 'conduit'" 2>/dev/null \
    | grep -o '"c": *[0-9]*' | grep -o '[0-9]*' | head -1
}

run_soak() {  # writes reward to stdout
  docker exec -e SOAK_TARGET=http://k3s:30800 \
              -e SOAK_CONFIG=/verifier/soak_config.json \
              -e REWARD_DIR=/logs/verifier \
              "$MAIN" bash /verifier/run_verifier.sh >/dev/null 2>&1
  docker exec "$MAIN" cat /logs/verifier/reward.txt 2>/dev/null
}

# Workload images the manifests reference (IfNotPresent). For a local run we
# import these into k3s's containerd so no registry pull is needed.
IMAGES="docker.io/library/postgres:16 \
docker.io/otel/opentelemetry-collector-contrib:0.116.1 \
ghcr.io/abundant-ai/logfire-service:latest \
ghcr.io/abundant-ai/conduit-otel:latest"

echo "### ensuring workload images are present on the host (pull if missing)"
for img in $IMAGES; do
  docker image inspect "$img" >/dev/null 2>&1 || docker pull --platform linux/arm64 "$img"
done

echo "### building + starting the two-service stack (k3s + main)"
$DC build >/dev/null
$DC up -d k3s >/dev/null
echo "### waiting for k3s healthy"
until docker exec "$K3S" kubectl get --raw=/readyz >/dev/null 2>&1; do sleep 3; done

# Import the images into k3s containerd (k8s.io ns) so IfNotPresent finds them.
# Critical for the two ghcr images (not public yet); the two public images can
# fall back to a runtime pull if the import doesn't take.
echo "### importing workload images into k3s containerd (k8s.io ns) for local IfNotPresent"
for img in $IMAGES; do
  echo -n "  import $img ... "
  if docker save "$img" | docker exec -i "$K3S" ctr -n k8s.io images import - >/dev/null 2>&1; then
    echo "ok"
  else
    echo "import skipped (public image will pull at runtime)"
  fi
done
# Any pods that already tried (and failed) to pull the not-yet-public ghcr images
# are retriggered now that those images are in containerd.
docker exec "$K3S" kubectl -n conduit delete pod --all --wait=false >/dev/null 2>&1 || true

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
sleep 4
N=$(count_conduit_spans)
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
  # re-arm the fault before each oracle run so it's a real fix each time, and let
  # the re-arm rollout FULLY converge (old RS -> 0, endpoint switched) so the run
  # starts from a settled faulty state.
  kubectl_k3s set env deploy/conduit WEB_CONCURRENCY=1 >/dev/null 2>&1
  kubectl_k3s rollout status deploy/conduit --timeout=180s >/dev/null 2>&1
  # wait until exactly one ReplicaSet is active + one Ready pod (endpoint settled)
  for _ in $(seq 1 45); do
    ACT=$(kubectl_k3s get rs -l app=conduit -o jsonpath='{range .items[?(@.status.replicas>0)]}x{end}' 2>/dev/null | wc -c | tr -d ' ')
    RDY=$(kubectl_k3s get po -l app=conduit --field-selector=status.phase=Running -o jsonpath='{range .items[*]}{.status.containerStatuses[0].ready}{"\n"}{end}' 2>/dev/null | grep -c true || true)
    [ "${ACT:-9}" -le 1 ] && [ "${RDY:-0}" -eq 1 ] && break
    sleep 2
  done
  until docker exec "$MAIN" curl -fsS -m3 http://k3s:30800/api/tags >/dev/null 2>&1; do sleep 2; done
  sleep 3
  docker exec "$MAIN" sh -c 'rm -f /workspace/findings.json'
  docker exec "$MAIN" bash /solve.sh >/dev/null 2>&1
  OR=$(run_soak); echo "  ORACLE run $r reward = $OR"
  [ "$OR" = "1.0" ] || ORACLE_OK=0
done

echo "======================================================"
echo "  NOP=$NOP   ORACLE=(x3 above)   oracle_all_pass=$ORACLE_OK"
[ "$NOP" = "0.0" ] && [ "$ORACLE_OK" = "1" ] && echo "  VALIDATION PASS (nop=0, oracle=1 x3)" || echo "  VALIDATION FAIL"
echo "======================================================"

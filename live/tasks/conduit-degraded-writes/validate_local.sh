#!/usr/bin/env bash
# Local validation of conduit-degraded-writes WITHOUT the Harbor runner.
# Brings the full compose stack up (project name = the task dir so the
# provisioner's hardcoded dokku container name resolves), then:
#   - confirms live spans reach logfire (service_name='conduit' rows via /v2/query)
#   - NOP:    faulty deployment, no fix, no findings   -> reward 0
#   - ORACLE: solution/solve.sh applies the fix + findings -> reward 1  (x3 for stability)
#
# Env: KEEP=1 leaves the stack up.
set -uo pipefail
cd "$(dirname "$0")"
TASK_DIR="$(pwd)"
PROJ=conduit-degraded-writes
ENVDIR="$TASK_DIR/environment"
DC="docker compose -p $PROJ -f $ENVDIR/docker-compose.yaml"
MAIN="$PROJ-main-1"
DOKKU="$PROJ-dokku-1"

cleanup() { [ "${KEEP:-0}" = "1" ] && { echo "KEEP=1 — leaving stack up"; return; }
  $DC down -v --remove-orphans >/dev/null 2>&1
  docker rm -f conduit.web.1 >/dev/null 2>&1 || true
  docker run --rm -v /var/lib:/vl alpine:3.20 rm -rf /vl/dokku-$PROJ >/dev/null 2>&1 || true
}
trap cleanup EXIT

query_logfire() {  # $1 = sql
  cat > /tmp/vq.json <<EOF
{"sql":"$1","min_timestamp":"2026-07-01T00:00:00Z"}
EOF
  docker cp /tmp/vq.json "$DOKKU:/tmp/vq.json" >/dev/null
  docker exec "$DOKKU" sh -c 'curl -s -X POST http://logfire:80/v2/query -H "Authorization: Bearer task-read-token" -H "Content-Type: application/json" --data @/tmp/vq.json'
}

run_soak() {  # writes reward to stdout
  docker exec -e SOAK_TARGET=http://conduit.web.1:8000 \
              -e SOAK_CONFIG=/verifier/soak_config.json \
              -e REWARD_DIR=/logs/verifier \
              "$MAIN" bash /verifier/run_verifier.sh >/dev/null 2>&1
  docker exec "$MAIN" cat /logs/verifier/reward.txt 2>/dev/null
}

echo "### building + starting the full stack"
$DC build >/dev/null
$DC up -d postgres logfire otel-collector dokku >/dev/null
until docker exec "$DOKKU" dokku version >/dev/null 2>&1; do sleep 2; done
echo "### provisioning (deploy conduit WITH the fault) — this builds the SUT"
$DC up provisioner
$DC up -d main >/dev/null
# wait for main entrypoint to see the marker + conduit healthy
until docker exec "$MAIN" test -f /mnt/state/provisioned 2>/dev/null; do sleep 2; done

echo "### drive a little load so spans exist, then confirm live spans in logfire"
docker exec "$DOKKU" sh -c 'for i in $(seq 1 12); do curl -s -o /dev/null http://conduit.web.1:8000/api/articles; done'
sleep 3
N=$(query_logfire "SELECT count(*) c FROM records WHERE service_name='conduit'" | grep -o '"c": [0-9]*' | grep -o '[0-9]*')
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
  docker exec "$DOKKU" dokku config:set conduit WEB_CONCURRENCY=1 >/dev/null 2>&1
  until docker exec "$DOKKU" curl -fsS -m3 http://conduit.web.1:8000/api/tags >/dev/null 2>&1; do sleep 2; done
  docker exec "$MAIN" sh -c 'rm -f /workspace/findings.json'
  docker exec "$MAIN" bash /solve.sh >/dev/null 2>&1
  OR=$(run_soak); echo "  ORACLE run $r reward = $OR"
  [ "$OR" = "1.0" ] || ORACLE_OK=0
done

echo "======================================================"
echo "  NOP=$NOP   ORACLE=(x3 above)   oracle_all_pass=$ORACLE_OK"
[ "$NOP" = "0.0" ] && [ "$ORACLE_OK" = "1" ] && echo "  VALIDATION PASS (nop=0, oracle=1 x3)" || echo "  VALIDATION FAIL"
echo "======================================================"

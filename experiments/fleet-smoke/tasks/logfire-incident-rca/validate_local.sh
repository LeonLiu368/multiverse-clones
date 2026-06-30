#!/usr/bin/env bash
# Local end-to-end check for logfire-incident-rca (no Harbor needed).
# Boots the gateway (prod-v1, baked corpus) + agent via compose, then runs the real
# verifier for nop (untouched) and oracle (solve.sh) and asserts reward 0 then 1.
#
#   COMPOSE_PROJECT_NAME=logfirefix ./validate_local.sh
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ENV="$HERE/environment"
export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-logfirefix}"

cat > "$ENV/compose-smoke.yaml" <<'YAML'
services:
  main:
    build: { context: ., dockerfile: Dockerfile }
    environment:
      - LOGFIRE_URL=http://logfire:80
      - LOGFIRE_TOKEN=test-token-acme-eval
      - LOGFIRE_MIN_TIMESTAMP=2026-06-24T00:00:00Z
    depends_on: { logfire: { condition: service_healthy } }
    command: ["sleep","infinity"]
  logfire:
    image: ghcr.io/abundant-ai/logfire-service:prod-v1
    build: { context: ., dockerfile: logfire.Dockerfile }
    environment: [ "LOGFIRE_TOKEN=test-token-acme-eval" ]
    expose: ["80"]
    healthcheck:
      test: ["CMD-SHELL","curl -fsS http://localhost:80/health || exit 1"]
      interval: 5s
      timeout: 5s
      retries: 20
      start_period: 20s
YAML
trap 'docker compose -f "$ENV/compose-smoke.yaml" down -v >/dev/null 2>&1; rm -f "$ENV/compose-smoke.yaml"' EXIT

docker compose -f "$ENV/compose-smoke.yaml" up -d --build
M="${COMPOSE_PROJECT_NAME}-main-1"
docker cp "$HERE/tests" "$M:/opt/tests" >/dev/null
docker cp "$HERE/solution/solve.sh" "$M:/opt/solve.sh" >/dev/null

docker exec "$M" bash /opt/tests/run_verifier.sh >/dev/null 2>&1
nop="$(docker exec "$M" cat /logs/verifier/reward.txt)"
echo "nop=$nop"

docker exec "$M" bash /opt/solve.sh >/dev/null 2>&1
docker exec "$M" bash /opt/tests/run_verifier.sh >/dev/null 2>&1
oracle="$(docker exec "$M" cat /logs/verifier/reward.txt)"
echo "oracle=$oracle"

[ "$nop" = "0" ] && [ "$oracle" = "1" ] && echo "PASS: nop=0 oracle=1" || { echo "FAIL"; exit 1; }

#!/bin/bash
# Local / CI harness for the bundled payments-incident task: boots the agent+gateway
# pair, asserts nop=0.0, runs the oracle, asserts oracle=1.0. Mirrors what Harbor does
# (Harbor builds `main` from environment/Dockerfile, merges environment/docker-compose
# over its base, mounts /logs, then runs tests/test.sh). Uses a unique project name to
# avoid colliding with parallel runs.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_DIR="$HERE/environment"
PROJECT="${COMPOSE_PROJECT_NAME:-sentryfix}"
CF="$ENV_DIR/.run_local.compose.yaml"

cleanup() {
  docker compose -p "$PROJECT" -f "$CF" down -v >/dev/null 2>&1 || true
  rm -f "$CF"
}
trap cleanup EXIT

# Merge: define main's build (Harbor supplies this) + the task's gateway service.
cat > "$CF" <<'YAML'
services:
  main:
    build:
      context: .
      dockerfile: Dockerfile
    image: sentryfix-agent:local
    environment:
      - SENTRY_URL=http://sentry
      - SENTRY_AUTH_TOKEN=test-token-acme-eval
      - SENTRY_ORG=acme
    depends_on:
      sentry:
        condition: service_healthy
    command: ["sleep", "infinity"]
  sentry:
    image: ghcr.io/abundant-ai/sentry-clone-service:empty
    build:
      context: .
      dockerfile: sentry.Dockerfile
    hostname: sentry
    environment:
      - SENTRY_CLONE_STATE_FILE=/data/sentry-clone/state.json
      - SENTRY_CLONE_RUNTIME_STATE_FILE=/var/lib/sentry-clone/state.json
      - SENTRY_CLONE_ENABLE_ADMIN_API=1
      - SENTRY_CLONE_ADMIN_TOKEN=test-admin-token-acme-eval
      - SENTRY_AUTH_TOKEN=test-token-acme-eval
      - SENTRY_ORG=acme
    volumes:
      - ./fixture.json:/data/sentry-clone/state.json:ro
    expose:
      - "80"
    healthcheck:
      test: ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://localhost/api/healthz', timeout=1).read()\""]
      interval: 2s
      timeout: 2s
      retries: 30
      start_period: 3s
YAML

dc() { docker compose -p "$PROJECT" -f "$CF" "$@"; }

dc up -d --build --wait --wait-timeout 120
dc exec -T -u root main mkdir -p /logs/verifier
dc exec -T -u root main chmod -R 777 /logs
dc cp "$HERE/tests" main:/tmp/tests
dc cp "$HERE/solution" main:/tmp/solution

dc exec -T main bash /tmp/tests/test.sh >/dev/null 2>&1 || true
nop="$(dc exec -T main cat /logs/verifier/reward.txt | tr -d '[:space:]')"
echo "nop reward=$nop"
[ "$nop" = "0" ] || { echo "FAIL: nop reward expected 0, got $nop"; exit 1; }

dc exec -T main bash /tmp/solution/solve.sh
dc exec -T main bash /tmp/tests/test.sh >/dev/null 2>&1 || true
oracle="$(dc exec -T main cat /logs/verifier/reward.txt | tr -d '[:space:]')"
echo "oracle reward=$oracle"
[ "$oracle" = "1" ] || { echo "FAIL: oracle reward expected 1, got $oracle"; exit 1; }

echo "PASS: nop=0.0 oracle=1.0"

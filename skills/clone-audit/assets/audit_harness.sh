#!/usr/bin/env bash
# audit_harness.sh — Phase 1 standup → health → baked-DB seed probe → isolation → image hygiene → teardown.
# Scaffold for clone-audit, centered on the agent + gateway runtime. Every check prints PASS/FAIL.
#
# Usage:
#   audit_harness.sh <compose-file> <gateway-service> <health-url-inside-net> [agent-state-path]
# Optional env:
#   AGENT_SVC=main           name of the agent (built) service
#   SEED_READ_URL=...        a seeded read on the gateway; non-empty body proves :prod-v1 baked-DB (R2.j)
#   GATEWAY_IMAGE=ghcr.io/<org>/<svc>-service:prod-v1   for the multi-arch check (R2.k)
#   ANSWER=...               a task answer string that must NOT be greppable in the agent image (R2.k leak)
#   AGENT_IMAGE=...          built agent image name for the leak grep
# Example:
#   SEED_READ_URL=http://figma:3000/v1/files/SEEDKEY GATEWAY_IMAGE=ghcr.io/abundant-ai/figma-service:prod-v1 \
#     audit_harness.sh environment/docker-compose.yaml figma http://figma:3000/health /srv/figma.db
set -uo pipefail

COMPOSE="${1:?compose file}"; SVC="${2:?gateway service name}"; HEALTH="${3:?health url}"
STATE_PATH="${4:-}"           # optional: seed path that must NOT exist in the agent container
AGENT_SVC="${AGENT_SVC:-main}"
pass=0; fail=0
ok()   { echo "PASS  $*"; pass=$((pass+1)); }
no()   { echo "FAIL  $*"; fail=$((fail+1)); }

dc() { docker compose -f "$COMPOSE" "$@"; }

echo "== cold boot =="
dc down -v >/dev/null 2>&1
if dc up --build -d; then ok "compose up"; else no "compose up"; echo "ABORT"; exit 1; fi

echo "== wait for healthy ($SVC) =="
healthy=""
for i in $(seq 1 60); do
  st=$(dc ps --format '{{.Service}} {{.Health}}' 2>/dev/null | awk -v s="$SVC" '$1==s{print $2}')
  [ "$st" = "healthy" ] && { healthy=1; break; }
  sleep 2
done
[ -n "$healthy" ] && ok "service healthy" || no "service never became healthy"

echo "== health reachable from agent over HTTP =="
if dc exec -T "$AGENT_SVC" sh -c "command -v curl >/dev/null && curl -fsS '$HEALTH' >/dev/null \
     || command -v wget >/dev/null && wget -qO- '$HEALTH' >/dev/null"; then
  ok "agent reaches $HEALTH by service name"
else
  no "agent could not reach $HEALTH"
fi

echo "== GHCR image DB seeding: gateway serves baked corpus (R2.j) =="
if [ -n "${SEED_READ_URL:-}" ]; then
  body=$(dc exec -T "$AGENT_SVC" sh -c "curl -fsS '$SEED_READ_URL' 2>/dev/null || wget -qO- '$SEED_READ_URL' 2>/dev/null")
  if [ -n "$body" ] && ! echo "$body" | grep -qiE '\"(items|data|nodes|results)\"[[:space:]]*:[[:space:]]*(\[\]|null)'; then
    ok "gateway returns seeded data from $SEED_READ_URL (baked-DB or mount serving)"
  else
    no "gateway returned empty seeded read — :prod-v1 may not bake the DB (R2.j)"
  fi
else
  echo "SKIP  set SEED_READ_URL to probe baked-DB seeding"
fi

echo "== image hygiene: gateway multi-arch (R2.k) =="
if [ -n "${GATEWAY_IMAGE:-}" ]; then
  arches=$(docker buildx imagetools inspect "$GATEWAY_IMAGE" 2>/dev/null | grep -i platform | tr -d ' ')
  if echo "$arches" | grep -qi amd64 && echo "$arches" | grep -qi arm64; then
    ok "$GATEWAY_IMAGE is multi-arch (amd64+arm64)"
  else
    no "$GATEWAY_IMAGE not multi-arch: ${arches:-<inspect failed/not pushed>}"
  fi
else
  echo "SKIP  set GATEWAY_IMAGE to check multi-arch"
fi

echo "== image hygiene: answer not greppable in agent (R2.k leak) =="
if [ -n "${ANSWER:-}" ] && [ -n "${AGENT_IMAGE:-}" ]; then
  if docker run --rm "$AGENT_IMAGE" grep -rsq "$ANSWER" /opt /app /usr/local; then
    no "LEAK: '$ANSWER' is greppable in $AGENT_IMAGE (R2.k)"
  else
    ok "answer not present in baked gateway source inside agent"
  fi
else
  echo "SKIP  set ANSWER + AGENT_IMAGE to run the leak grep"
fi

echo "== isolation: no seed on disk in agent (R2.g/c) =="
if [ -n "$STATE_PATH" ]; then
  if dc exec -T "$AGENT_SVC" sh -c "[ ! -e '$STATE_PATH' ]"; then
    ok "agent has no seed at $STATE_PATH (SEALED)"
  else
    no "LEAK: $STATE_PATH exists in agent container"
  fi
else
  echo "SKIP  no state-path given"
fi

echo "== compose has no 'networks:' block unless documented (R1.4/R2.f) =="
if grep -qE '^[[:space:]]*networks:' "$COMPOSE"; then
  no "'networks:' present — confirm a documented isolation exception"
else
  ok "no 'networks:' block"
fi

echo "== teardown =="
dc down -v >/dev/null 2>&1 && ok "compose down -v" || no "teardown"

echo "----------------------------------------"
echo "harness: $pass passed, $fail failed"
echo "NOTE: nop/oracle (R1.3) are measured separately via tests/test.sh + solution/solve.sh."
[ "$fail" -eq 0 ]

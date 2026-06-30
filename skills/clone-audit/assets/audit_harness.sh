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

# A Harbor task compose omits main's build (Harbor injects it). If `main` has no build/image here,
# auto-merge the override asset so the pair boots standalone (the #1 auditor blocker). Override-path:
# set EXTRA_COMPOSE to a space-separated list of extra -f files, or drop harbor-main-build.override.yaml
# next to this script.
EXTRA_COMPOSE="${EXTRA_COMPOSE:-}"
_here="$(cd "$(dirname "$0")" && pwd)"
if ! grep -qE '^[[:space:]]*(build|image):' <(awk '/^[[:space:]]*main:/{f=1} f&&/^[[:space:]]*[a-z_]+:/&&!/main:/{exit} f' "$COMPOSE") 2>/dev/null; then
  if [ -f "$_here/harbor-main-build.override.yaml" ]; then
    EXTRA_COMPOSE="$EXTRA_COMPOSE $_here/harbor-main-build.override.yaml"
    echo "INFO  main has no build/image — merging harbor-main-build.override.yaml"
  else
    echo "WARN  main has no build/image and no override found; standalone boot may fail (see asset)"
  fi
fi
# Isolate the compose project so PARALLEL fleet audits don't collide (a real failure seen in a
# fleet run: one clone's agent came up on another clone's image because both used the compose dir's
# default project name). Derive a unique, stable name from the clone/compose path.
: "${COMPOSE_PROJECT_NAME:=audit_$(printf '%s' "$(cd "$(dirname "$COMPOSE")" && pwd)" | tr -c 'a-z0-9' '_' | tail -c 40)}"
export COMPOSE_PROJECT_NAME
echo "INFO  COMPOSE_PROJECT_NAME=$COMPOSE_PROJECT_NAME"
_files=(-f "$COMPOSE"); for f in $EXTRA_COMPOSE; do _files+=(-f "$f"); done
dc() { docker compose -p "$COMPOSE_PROJECT_NAME" "${_files[@]}" "$@"; }

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

echo "== image hygiene: no leak in agent — grep + import + source (R2.k) =="
if [ -n "${AGENT_IMAGE:-}" ]; then
  # (1) literal answer grep
  if [ -n "${ANSWER:-}" ] && docker run --rm "$AGENT_IMAGE" grep -rsq "$ANSWER" /opt /app /usr/local; then
    no "LEAK(grep): '$ANSWER' is greppable in $AGENT_IMAGE"
  else
    ok "answer not greppable in agent ${ANSWER:+}"
  fi
  # (2) seed generator must NOT be importable — the recomputable-answer leak grep misses
  if [ -n "${PKG:-}" ]; then
    if docker run --rm "$AGENT_IMAGE" python -c "import ${PKG}.seed" 2>/dev/null; then
      no "LEAK(import): ${PKG}.seed is importable in the agent — generator can recompute the world"
    else
      ok "${PKG}.seed not importable in agent"
    fi
  else
    echo "SKIP  set PKG to test seed-generator import-reachability"
  fi
  # (3) no api/ or seed/ source dirs survive in the agent
  if docker run --rm "$AGENT_IMAGE" sh -c 'find /opt /app -path "*/seed/*" -o -path "*/api/*" 2>/dev/null | grep -q .'; then
    no "LEAK(source): api/ or seed/ source present in $AGENT_IMAGE — strip it from the agent Dockerfile"
  else
    ok "no api/ or seed/ source in agent"
  fi
else
  echo "SKIP  set AGENT_IMAGE to run the leak checks"
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

#!/usr/bin/env bash
# audit_harness.sh — Phase 1 standup → health-probe → isolation check → teardown.
# Scaffold for clone-audit. Extend the PROBES section per clone. Every check prints PASS/FAIL.
#
# Usage:
#   audit_harness.sh <compose-file> <service-name> <health-url-inside-net> [state-path-in-agent]
# Example:
#   audit_harness.sh environment/docker-compose.yaml figma http://figma:80/health /data/figma/state.json
set -uo pipefail

COMPOSE="${1:?compose file}"; SVC="${2:?service name}"; HEALTH="${3:?health url}"
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

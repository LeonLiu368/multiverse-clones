#!/usr/bin/env bash
# Thin agent entrypoint. The Jira/ENG corpus is the `jira` sidecar (no service runs here).
# Wait for the sidecar's /health to be reachable, then keep the container alive for the agent.
set -uo pipefail
BASE="${PLANE_BASE_URL:-http://jira:8765}"
for _ in $(seq 1 60); do
  curl -sf "$BASE/health" >/dev/null 2>&1 && break
  sleep 1
done
echo "[agent] jira corpus reachable at $BASE — tools ready (jira CLI + linear CLI)"
exec tail -f /dev/null

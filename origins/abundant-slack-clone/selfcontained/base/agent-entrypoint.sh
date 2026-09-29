#!/usr/bin/env bash
# Thin agent entrypoint. The Slack workspace is the `slack` sidecar (no gateway runs here).
# Wait for the sidecar to be reachable, then keep the container alive for the agent.
set -uo pipefail
BASE="${SLACK_API_URL:-http://slack}"
for _ in $(seq 1 60); do
  curl -s "$BASE/api/auth.test" >/dev/null 2>&1 && break
  sleep 1
done
echo "[agent] slack workspace reachable at $BASE — tools ready (slack CLI + slack-mcp)"
exec tail -f /dev/null

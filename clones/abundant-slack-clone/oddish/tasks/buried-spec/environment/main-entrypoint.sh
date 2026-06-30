#!/usr/bin/env bash
# Thin agent entrypoint for the two-container task. NO gateway runs here — the Slack workspace is the
# `slack` sidecar. Wait for it to be reachable, then keep the container alive for the agent. The
# agent's tools (the `slack` CLI and the korotovsky `slack-mcp` server) both talk to the gateway at
# $SLACK_API_URL (http://slack).
set -uo pipefail
BASE="${SLACK_API_URL:-http://slack}"
for _ in $(seq 1 60); do
  curl -s "$BASE/api/auth.test" >/dev/null 2>&1 && break
  sleep 1
done
echo "[main] slack workspace reachable at $BASE — agent tools available (slack CLI + slack-mcp)"
exec tail -f /dev/null

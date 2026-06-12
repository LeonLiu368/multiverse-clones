#!/usr/bin/env bash
# Single-container entrypoint for the task `main` container: import the seed into SQLite, start the
# Slack gateway on :80, then keep the container alive for the agent. The agent's tools (the `slack`
# CLI and the korotovsky `slack-mcp` server) both talk to the gateway at http://localhost.
set -uo pipefail
source /usr/local/bin/slack-boot.sh
echo "[main] gateway ready — agent tools available (slack CLI + slack-mcp)"
exec tail -f /dev/null

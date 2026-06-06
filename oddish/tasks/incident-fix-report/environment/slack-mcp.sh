#!/usr/bin/env bash
# `slack` MCP launcher (stdio). The agent runtime starts this as the `slack` MCP server
# (declared in task.toml [environment].mcp_servers). It authenticates the workspace
# connection, then hands stdio to the MCP server that exposes the workspace tools.
#
# IMPORTANT: write nothing to stdout (stdout is the MCP JSON-RPC channel). Diagnostics -> stderr.
set -uo pipefail
URL="${MM_URL:-http://mattermost:8065}"
USER_ID="${MM_ADMIN_USER:-admin@demo.local}"
PASS="${MM_ADMIN_PASS:-AdminUser123!}"

for _ in $(seq 1 60); do
  if mmctl auth login "$URL" --name local --username "$USER_ID" --password "$PASS" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

exec mmctl-mcp

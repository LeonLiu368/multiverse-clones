#!/usr/bin/env bash
# MCP launcher (stdio). The agent runtime starts this as the `mattermost` MCP server
# (declared in task.toml [environment].mcp_servers). It ensures mmctl is authenticated
# against the Mattermost server over the REMOTE (TCP) auth context — idempotently — then
# hands stdio to the mmctl-mcp server. Mirrors APEX's bin/mcp-* wrapper pattern.
#
# IMPORTANT: write nothing to stdout here (stdout is the MCP JSON-RPC channel). All
# diagnostics go to stderr.
set -uo pipefail
URL="${MM_URL:-http://mattermost:8065}"
USER_ID="${MM_ADMIN_USER:-admin@demo.local}"
PASS="${MM_ADMIN_PASS:-AdminUser123!}"

# Wait briefly for the server, then (re)establish the remote auth context.
for _ in $(seq 1 60); do
  if mmctl auth login "$URL" --name local --username "$USER_ID" --password "$PASS" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

exec mmctl-mcp

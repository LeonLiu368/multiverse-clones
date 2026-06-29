#!/bin/sh
# Wrapper for the korotovsky slack-mcp-server, launched by the agent harness over stdio.
#
# stdio MCP clients spawn the server with get_default_environment() (only HOME+PATH), stripping the
# container's SLACK_BOT_TOKEN. Recover it from PID 1 (carries the compose `environment:` + image
# ENV), then map our single-container config onto the env korotovsky expects:
#   - XOXP (user-token) mode  -> enables the search tool (disabled for xoxb bot tokens) and the
#     standard Web API path (not the edge API). Our gateway accepts any token string == SLACK_BOT_TOKEN.
#   - SLACK_MCP_API_URL        -> our gateway (the in-image patch applies this to the first auth.test).
#   - SLACK_MCP_ENABLED_TOOLS  -> only the tools our gateway backs (all standard Web API, no edge).
set -e

pid1() { tr '\0' '\n' < /proc/1/environ 2>/dev/null | sed -n "s/^$1=//p" | head -1; }

TOKEN="$(pid1 SLACK_BOT_TOKEN)"; TOKEN="${TOKEN:-${SLACK_BOT_TOKEN:-xoxp-acme-eval-0001}}"
APIURL="$(pid1 SLACK_API_URL)"; APIURL="${APIURL:-${SLACK_API_URL:-http://localhost}}"

export SLACK_MCP_XOXP_TOKEN="$TOKEN"
export SLACK_MCP_API_URL="${APIURL%/}/api/"
export SLACK_MCP_ENABLED_TOOLS="conversations_history,conversations_replies,channels_list,conversations_search_messages,conversations_add_message"
export SLACK_MCP_ADD_MESSAGE_TOOL="true"

exec /usr/local/bin/slack-mcp-server-bin --transport stdio

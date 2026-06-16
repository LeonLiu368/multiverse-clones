# Agent container (Harbor `main`) — FROM the published thin agent base; adds only this task's
# codebase. Tools-only (slack CLI + korotovsky MCP), no gateway, no data: the Slack workspace lives
# in the `slack` sidecar (see docker-compose.yaml), reachable only over HTTP at http://slack. The
# agent has no filesystem access to the chat data, so it can't bypass the tools.
FROM ghcr.io/abundant-ai/slack-agent:slack-mcp-oss
COPY codebase /workspace

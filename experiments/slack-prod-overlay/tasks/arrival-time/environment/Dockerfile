# Agent container (Harbor `main`) — FROM the published thin agent base; adds only the codebase.
# Tools-only (slack CLI + korotovsky MCP), no gateway, no data: the Slack workspace is the shared
# `slack` prod sidecar (see docker-compose.yaml), reachable only over HTTP at http://slack.
FROM ghcr.io/abundant-ai/slack-agent:slack-mcp-oss
COPY codebase /workspace

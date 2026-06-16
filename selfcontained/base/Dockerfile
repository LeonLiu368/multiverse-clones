# Agent container (Harbor `main`) — built FROM the published thin agent base; adds only this task's
# codebase. Tools-only (slack CLI + korotovsky MCP), no gateway, no data: the Slack workspace lives
# in the `slack` sidecar (see docker-compose.yaml) and is reachable only over HTTP at http://slack.
FROM ghcr.io/abundant-ai/slack-agent:slack-mcp-oss
COPY codebase /workspace

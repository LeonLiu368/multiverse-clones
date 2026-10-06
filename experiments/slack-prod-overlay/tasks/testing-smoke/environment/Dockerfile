# Agent container (Harbor `main`) — FROM the thin agent base; adds only the codebase. Tools-only.
# Workspace is the `slack` sidecar (WorldsDataTest corpus + this task's overlay) at http://slack.
FROM ghcr.io/abundant-ai/slack-agent:slack-mcp-oss
COPY codebase /workspace

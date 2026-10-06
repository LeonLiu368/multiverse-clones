# Agent container (Harbor `main`) — thin agent base + codebase only. Tools-only; the workspace is the
# `slack` sidecar (shared prod corpus + this task's recent overlay), reachable at http://slack.
FROM ghcr.io/abundant-ai/slack-agent:slack-mcp-oss
COPY codebase /workspace

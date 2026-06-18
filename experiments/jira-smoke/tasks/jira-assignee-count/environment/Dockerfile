# Agent (`main`) container for the jira-assignee-count task. Built FROM the thin jira-agent base
# (jira/linear CLI only — NO service, NO state.json). The WEB project lives only in the `jira`
# sidecar (jira-gateway:empty + a mounted state.json); this container reaches it over HTTP via the
# `jira` CLI in remote/agent mode (PLANE_BASE_URL=http://jira:8765).
FROM --platform=linux/amd64 ghcr.io/abundant-ai/jira-agent:latest

COPY codebase /workspace
WORKDIR /workspace
# base ENTRYPOINT (agent-entrypoint.sh) waits for the jira sidecar, then keeps the box alive.

# Agent/client image (the `client` service). The agent's tools are:
#   - mmctl          : the official Mattermost CLI (copied from the Mattermost image)
#   - mmctl-mcp      : an MCP server exposing ~60 mmctl tools (built from source, patched)
# curl+jq are included for the split-harness verifier.

# --- Stage 1: the exact-version mmctl binary, straight from the Mattermost product image.
FROM mattermost/mattermost-team-edition:8.1.1 AS mmsrc

# --- Stage 2: build mmctl-mcp (the official MCP wrapper for mmctl) from pinned source.
# PATCH: upstream hard-codes `mmctl --local` (a unix socket on the SERVER host), which is
# unreachable from this separate client container. We drop the forced --local so every tool
# uses mmctl's configured REMOTE auth context (TCP -> http://mattermost:8065) — the same
# transport mmctl + the verifier already use, and the portable/Harbor-compatible path.
FROM golang:1.24-bookworm AS mcpbuild
ARG MMCTL_MCP_SHA=cdfde430b0ef7225481a5c0b0ff28f914aa0a1dc
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
WORKDIR /src
RUN git clone https://github.com/mattermost/mmctl-mcp.git . && git checkout ${MMCTL_MCP_SHA}
RUN sed -i 's|append(\[\]string{"--local"}, args...)|args|' main.go \
 && sed -i 's|Run any mmctl command with --local mode|Run any mmctl command (uses the configured remote mmctl auth context)|' main.go
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -trimpath -o /out/mmctl-mcp .

# --- Final stage: the client/agent image.
FROM debian:bookworm-slim
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl jq ca-certificates bash && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

COPY --from=mmsrc /mattermost/bin/mmctl /usr/local/bin/mmctl
COPY --from=mcpbuild /out/mmctl-mcp /usr/local/bin/mmctl-mcp

COPY client-entrypoint.sh /usr/local/bin/client-entrypoint.sh
COPY mcp-mmctl.sh /usr/local/bin/mcp-mmctl
RUN chmod +x /usr/local/bin/client-entrypoint.sh /usr/local/bin/mcp-mmctl

ENV MM_URL=http://mattermost:8065 \
    MM_TEAM=test-demo \
    MM_ADMIN_USER=admin@demo.local \
    MM_ADMIN_PASS=AdminUser123!

WORKDIR /app
# Authenticates mmctl as admin, waits until #incidents is seeded, then stays alive so the
# agent can drop in with mmctl already configured (and mmctl-mcp ready over stdio).
ENTRYPOINT ["/usr/local/bin/client-entrypoint.sh"]

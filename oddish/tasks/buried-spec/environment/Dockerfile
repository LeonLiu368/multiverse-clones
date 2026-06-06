# Agent/client image (the `client` service). The agent sees a Slack-branded surface:
#   - slack          : a `slack` CLI (Slack Web API-style methods) wrapping mmctl
#   - slack (MCP)    : a `slack` MCP server (slack-mcp -> mmctl-mcp)
# Underlying (hidden from the agent): mmctl + mmctl-mcp. curl+jq are for the verifier.

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
# Includes python3 + pytest to run the /workspace codebase's test suite.
FROM debian:bookworm-slim
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl jq ca-certificates bash \
        python3 python3-pytest git && \
    ln -sf /usr/bin/python3 /usr/local/bin/python && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Underlying tooling (hidden from the agent): the official mmctl CLI + the mmctl-mcp server.
COPY --from=mmsrc /mattermost/bin/mmctl /usr/local/bin/mmctl
COPY --from=mcpbuild /out/mmctl-mcp /usr/local/bin/mmctl-mcp

# The Slack-branded surface the agent actually uses: a `slack` CLI (Slack Web API style)
# and a `slack` MCP launcher, both thin wrappers over the tooling above.
COPY client-entrypoint.sh /usr/local/bin/client-entrypoint.sh
COPY slack /usr/local/bin/slack
COPY slack-mcp.sh /usr/local/bin/slack-mcp
RUN chmod +x /usr/local/bin/client-entrypoint.sh /usr/local/bin/slack /usr/local/bin/slack-mcp

# The codebase the agent works on.
COPY codebase /workspace

ENV MM_URL=http://mattermost:8065 \
    MM_TEAM=test-demo \
    MM_ADMIN_USER=admin@demo.local \
    MM_ADMIN_PASS=AdminUser123!

WORKDIR /workspace
# Authenticates the workspace connection, waits until the workspace is seeded, then stays
# alive so the agent can drop in with `slack` (CLI + MCP) already configured.
ENTRYPOINT ["/usr/local/bin/client-entrypoint.sh"]

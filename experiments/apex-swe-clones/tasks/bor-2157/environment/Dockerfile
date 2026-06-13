# Agent image for bor-2157 (clone-based observability task).
# 0xPolygon/bor checked out at the buggy parent of PR #2157 in /app/repo; the
# ticketvector / slack / gauge agent tools are layered in from the clone images.
FROM ghcr.io/abundant-ai/ticketvector-service:main AS tv-tools
FROM ghcr.io/abundant-ai/slack-service:latest AS slack-tools
FROM ghcr.io/abundant-ai/gauge-service:main AS gauge-tools

FROM golang:1.26
ENV GOTOOLCHAIN=auto
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        git curl jq patch ca-certificates python3 \
    && rm -rf /var/lib/apt/lists/*

# Issue tracker CLI (linear/jira), team chat (slack + slack-mcp), observability (gcx + mcp-grafana).
COPY --from=tv-tools /usr/local/bin/linear /usr/local/bin/jira /usr/local/bin/
COPY --from=tv-tools /opt/ticketvector /opt/ticketvector
COPY --from=slack-tools /usr/local/bin/slack /usr/local/bin/slack-mcp /usr/local/bin/
COPY --from=slack-tools /opt/slackcli /opt/slackcli
COPY --from=gauge-tools /usr/local/bin/gcx /usr/local/bin/mcp-grafana /usr/local/bin/
COPY --from=gauge-tools /opt/gaugecli /opt/gaugecli
RUN chmod +x /usr/local/bin/linear /usr/local/bin/jira /usr/local/bin/slack \
             /usr/local/bin/slack-mcp /usr/local/bin/gcx /usr/local/bin/mcp-grafana

# Target repo at the buggy base commit; warm the Go module + build cache.
WORKDIR /app
RUN git clone --filter=blob:none https://github.com/0xPolygon/bor.git repo \
 && cd repo && git checkout 2a0bfe7f3db8333ca27e9269f27b0e86b49a3913
WORKDIR /app/repo
RUN go mod download || true
RUN go build ./... || true

ENV PYTHONPATH=/opt:/opt/ticketvector:/opt/slackcli:/opt/gaugecli \
    WORLD_ISSUES_BACKEND=remote \
    WORLD_ISSUES_OUTPUT=json \
    WORLD_ISSUES_AGENT_MODE=1 \
    WORLD_ISSUES_ACTOR=agent \
    WORLD_ISSUES_DEFAULT_PROJECT=BOR \
    PLANE_BASE_URL=http://127.0.0.1:8765 \
    SLACK_API_URL=http://slack \
    SLACK_BOT_TOKEN=test-token-meridian-eval \
    GRAFANA_URL=http://gauge \
    GRAFANA_TOKEN=test-token-meridian-eval \
    GRAFANA_SERVICE_ACCOUNT_TOKEN=test-token-meridian-eval
WORKDIR /app/repo
CMD ["sleep", "infinity"]

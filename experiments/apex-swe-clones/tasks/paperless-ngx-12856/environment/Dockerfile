# Agent image for paperless-ngx-12856 (clone-based observability task).
# paperless-ngx checked out at the buggy parent of PR #12856 in /app/repo; the
# ticketvector / slack / gauge agent tools are layered in from the clone images.
FROM ghcr.io/abundant-ai/ticketvector-service:main AS tv-tools
FROM ghcr.io/abundant-ai/slack-service:latest AS slack-tools
FROM ghcr.io/abundant-ai/gauge-service:main AS gauge-tools

FROM python:3.12
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        git curl jq patch build-essential libpq-dev libmagic1 ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv

# Issue tracker CLI (linear/jira), team chat (slack + slack-mcp), observability (gcx + mcp-grafana).
COPY --from=tv-tools /usr/local/bin/linear /usr/local/bin/jira /usr/local/bin/
COPY --from=tv-tools /opt/ticketvector /opt/ticketvector
COPY --from=slack-tools /usr/local/bin/slack /usr/local/bin/slack-mcp /usr/local/bin/
COPY --from=slack-tools /opt/slackcli /opt/slackcli
COPY --from=gauge-tools /usr/local/bin/gcx /usr/local/bin/mcp-grafana /usr/local/bin/
COPY --from=gauge-tools /opt/gaugecli /opt/gaugecli
RUN chmod +x /usr/local/bin/linear /usr/local/bin/jira /usr/local/bin/slack \
             /usr/local/bin/slack-mcp /usr/local/bin/gcx /usr/local/bin/mcp-grafana

# Target repo at the buggy base commit.
WORKDIR /app
RUN git clone --filter=blob:none https://github.com/paperless-ngx/paperless-ngx.git repo \
 && cd repo && git checkout 4ce5f2022c82cf244a08ca797236abbe5dee0390
WORKDIR /app/repo
ENV UV_PROJECT_ENVIRONMENT=/app/repo/.venv
RUN uv sync --frozen --no-default-groups --group testing || uv sync --no-default-groups --group testing || true

ENV PYTHONPATH=/opt:/opt/ticketvector:/opt/slackcli:/opt/gaugecli \
    WORLD_ISSUES_BACKEND=remote \
    WORLD_ISSUES_OUTPUT=json \
    WORLD_ISSUES_AGENT_MODE=1 \
    WORLD_ISSUES_ACTOR=agent \
    WORLD_ISSUES_DEFAULT_PROJECT=OPS \
    PLANE_BASE_URL=http://127.0.0.1:8765 \
    SLACK_API_URL=http://slack \
    SLACK_BOT_TOKEN=test-token-meridian-eval \
    GRAFANA_URL=http://gauge \
    GRAFANA_TOKEN=test-token-meridian-eval \
    GRAFANA_SERVICE_ACCOUNT_TOKEN=test-token-meridian-eval
WORKDIR /app/repo
CMD ["sleep", "infinity"]

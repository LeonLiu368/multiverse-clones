# Agent (Harbor `main`) image for variant-paperless-ngx-12865-chat-tickets.
#
# Contains the paperless-ngx repo at the BUGGY base commit at /app/repo, plus the two
# client toolsets the agent uses to investigate the incident — both pulled straight
# from their published service images (nothing vendored into this repo):
#   * linear / jira / world-issues  (ticketvector-service)  -> http://ticketvector:8765
#   * slack / slack-mcp             (slack-service)          -> http://slack
# The seeded incident data is NOT in this image; it lives in the sidecars and is
# reachable only through the tools above.
FROM python:3.12

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        git curl jq patch build-essential libpq-dev libmagic1 ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv

# --- ticketvector CLIs (zero third-party deps; remote mode is stdlib-only) ---
# Pinned to the SAME digest the ticketvector sidecar runs, so client and server match.
COPY --from=ghcr.io/abundant-ai/ticketvector-service@sha256:89d4bdf0624fee83464491563ec53a0a816273bfd0ebca95afeb78159d2e2ee9 \
     /opt/ticketvector /opt/ticketvector
RUN ln -sf /opt/ticketvector/world-issues /usr/local/bin/world-issues \
 && ln -sf /opt/ticketvector/linear       /usr/local/bin/linear \
 && ln -sf /opt/ticketvector/jira         /usr/local/bin/jira \
 && chmod +x /opt/ticketvector/world-issues /opt/ticketvector/linear /opt/ticketvector/jira

# --- slack CLI + slack-mcp (the slackcli package + its two entry-point shims) ---
COPY --from=ghcr.io/abundant-ai/slack-service@sha256:13d7f7892e971154f9643cd660ac12bee6f45ce8012d6212f8f2ef8db3dcacae \
     /opt/slackcli /opt/slackcli
COPY --from=ghcr.io/abundant-ai/slack-service@sha256:13d7f7892e971154f9643cd660ac12bee6f45ce8012d6212f8f2ef8db3dcacae \
     /usr/local/bin/slack /usr/local/bin/slack
COPY --from=ghcr.io/abundant-ai/slack-service@sha256:13d7f7892e971154f9643cd660ac12bee6f45ce8012d6212f8f2ef8db3dcacae \
     /usr/local/bin/slack-mcp /usr/local/bin/slack-mcp
RUN pip install --no-cache-dir "slack_sdk>=3.27" "mcp>=1.2" \
 && chmod +x /usr/local/bin/slack /usr/local/bin/slack-mcp

# Tool wiring: CLIs reach the sidecars by compose service name.
ENV PYTHONPATH=/opt/ticketvector:/opt/slackcli \
    SLACK_API_URL=http://slack \
    SLACK_BOT_TOKEN=xoxb-acme-eval-0001 \
    WORLD_ISSUES_BACKEND=remote \
    PLANE_BASE_URL=http://ticketvector:8765 \
    WORLD_ISSUES_AGENT_MODE=1 \
    WORLD_ISSUES_OUTPUT=json

# --- target repo at the buggy base commit ---
WORKDIR /app
RUN git clone --filter=blob:none https://github.com/paperless-ngx/paperless-ngx.git repo \
 && cd repo && git checkout 97e3c7572018f071956ee735db44c27f11d37bc7
WORKDIR /app/repo
# Prefetch the test environment so the agent/verifier can run the suite.
ENV UV_PROJECT_ENVIRONMENT=/app/repo/.venv
RUN uv sync --frozen --no-default-groups --group testing || uv sync --no-default-groups --group testing || true

WORKDIR /app/repo
CMD ["sleep", "infinity"]

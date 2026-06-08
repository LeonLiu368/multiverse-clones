# Three-surface-ops task: all three service CLIs available in main.
FROM ghcr.io/abundant-ai/slack-service@sha256:13d7f7892e971154f9643cd660ac12bee6f45ce8012d6212f8f2ef8db3dcacae AS slack-tools
FROM ghcr.io/abundant-ai/ticketvector-service@sha256:89d4bdf0624fee83464491563ec53a0a816273bfd0ebca95afeb78159d2e2ee9 AS ticketvector-tools

# ghc-service is the runtime base: Python 3.11 + gh/ghc/ghclone already baked in, lives on
# GHCR so there are no Docker Hub pull-rate-limit issues.
FROM ghcr.io/abundant-ai/ghc-service@sha256:d4e88d7fa4af0ae84213d54f4b884b3a8954ebad9fe88b6f6fb97cea1443b3cf

# jq is the only tool not already present in the base image (git/curl/bash/pip3 are there).
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    jq && rm -rf /var/lib/apt/lists/*

# gh/ghc/ghclone are already in the base — only copy the other two surface toolkits.

# Slack CLI + MCP server
COPY --from=slack-tools /opt/slackcli /opt/slackcli
COPY --from=slack-tools /usr/local/bin/slack /usr/local/bin/slack
COPY --from=slack-tools /usr/local/bin/slack-mcp /usr/local/bin/slack-mcp

# Ticketvector CLIs (world-issues, linear, jira)
COPY --from=ticketvector-tools /opt/ticketvector /opt/ticketvector
RUN ln -sf /opt/ticketvector/world-issues /usr/local/bin/world-issues \
 && ln -sf /opt/ticketvector/linear /usr/local/bin/linear \
 && ln -sf /opt/ticketvector/jira /usr/local/bin/jira \
 && chmod +x /opt/ticketvector/world-issues /opt/ticketvector/linear /opt/ticketvector/jira

RUN pip install --no-cache-dir httpx typer rich pydantic platformdirs jq "slack_sdk>=3.27" "mcp>=1.2"

# Service endpoints — token for github auto-read from /run/secrets/token
ENV PYTHONPATH=/opt/ticketvector:/opt/slackcli:/opt \
    GH_HOST=http://github \
    SLACK_API_URL=http://slack \
    SLACK_BOT_TOKEN=xoxb-acme-eval-0001 \
    WORLD_ISSUES_BACKEND=remote \
    PLANE_BASE_URL=http://ticketvector:8765 \
    WORLD_ISSUES_AGENT_MODE=1 \
    WORLD_ISSUES_OUTPUT=json

RUN git config --system user.email agent@local && git config --system user.name agent

WORKDIR /app
CMD ["sleep", "infinity"]

# Agent image for exact APEX paperless-ngx-10555 on the clone stack.
# The upstream repo snapshot is fetched from the public mercor/APEX-SWE dataset at build
# (APEX ships no base_commit — repo/ is a vendored snapshot); clone agent tools are layered in.
FROM ghcr.io/abundant-ai/ticketvector-service:main AS tv-tools
FROM ghcr.io/abundant-ai/slack-service:latest AS slack-tools
FROM ghcr.io/abundant-ai/gauge-service:main AS gauge-tools

# Docker Hub mirror (mirror.gcr.io) to dodge unauthenticated pull rate limits (429).
FROM mirror.gcr.io/library/python:3.11
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        git build-essential curl jq ca-certificates \
        libpoppler-cpp-dev poppler-utils ghostscript imagemagick optipng \
        unpaper qpdf tesseract-ocr tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv "huggingface_hub>=0.25"

# Issue tracker CLI (linear/jira), team chat (slack + slack-mcp), observability (gcx + mcp-grafana).
COPY --from=tv-tools /usr/local/bin/linear /usr/local/bin/jira /usr/local/bin/
COPY --from=tv-tools /opt/ticketvector /opt/ticketvector
COPY --from=slack-tools /usr/local/bin/slack /usr/local/bin/slack-mcp /usr/local/bin/
COPY --from=slack-tools /opt/slackcli /opt/slackcli
COPY --from=gauge-tools /usr/local/bin/gcx /usr/local/bin/mcp-grafana /usr/local/bin/
COPY --from=gauge-tools /opt/gaugecli /opt/gaugecli
RUN chmod +x /usr/local/bin/linear /usr/local/bin/jira /usr/local/bin/slack \
             /usr/local/bin/slack-mcp /usr/local/bin/gcx /usr/local/bin/mcp-grafana

# Fetch the upstream repo snapshot from the APEX dataset, then build it.
ARG APEX_TASK=Observability/paperless-ngx-paperless-ngx-10195-10196-observability
RUN python - <<PY
from huggingface_hub import snapshot_download
snapshot_download(repo_id="mercor/APEX-SWE", repo_type="dataset",
                  allow_patterns=["${APEX_TASK}/repo/**"], local_dir="/tmp/apex")
PY
RUN mkdir -p /app && cp -a "/tmp/apex/${APEX_TASK}/repo" /app/repo && rm -rf /tmp/apex
WORKDIR /app/repo
ENV UV_PROJECT_ENVIRONMENT=/usr/local
RUN uv sync --all-groups || uv sync || true
# the slack CLI (copied from slack-service) imports slack_sdk — install it into the env
RUN pip install --no-cache-dir slack_sdk
RUN git init -q && git config user.email agent@example.local && git config user.name "Agent User" \
 && git add -A && git commit -q -m "snapshot" || true

ENV PYTHONPATH=/opt:/opt/ticketvector:/opt/slackcli:/opt/gaugecli \
    WORLD_ISSUES_BACKEND=remote \
    WORLD_ISSUES_OUTPUT=json \
    WORLD_ISSUES_AGENT_MODE=1 \
    WORLD_ISSUES_ACTOR=agent \
    WORLD_ISSUES_DEFAULT_PROJECT=PNGX \
    PLANE_BASE_URL=http://127.0.0.1:8765 \
    SLACK_API_URL=http://slack \
    SLACK_BOT_TOKEN=test-token-meridian-eval \
    GRAFANA_URL=http://gauge \
    GRAFANA_TOKEN=test-token-meridian-eval \
    GRAFANA_SERVICE_ACCOUNT_TOKEN=test-token-meridian-eval
WORKDIR /app/repo
CMD ["sleep", "infinity"]

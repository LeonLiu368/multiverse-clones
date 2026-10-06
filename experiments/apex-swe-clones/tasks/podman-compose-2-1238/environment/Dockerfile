# Agent image for exact APEX containers-podman-compose-2-1238 on the clone stack.
# Repo snapshot fetched from the public mercor/APEX-SWE dataset at build; clone tools layered in.
FROM ghcr.io/abundant-ai/ticketvector-service:main AS tv-tools
FROM ghcr.io/abundant-ai/slack-service:latest AS slack-tools
FROM ghcr.io/abundant-ai/gauge-service:main AS gauge-tools

# Docker Hub mirror (mirror.gcr.io) to dodge unauthenticated pull rate limits (429).
FROM mirror.gcr.io/library/python:3.11
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        git build-essential curl jq ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir "huggingface_hub>=0.25"

COPY --from=tv-tools /usr/local/bin/linear /usr/local/bin/jira /usr/local/bin/
COPY --from=tv-tools /opt/ticketvector /opt/ticketvector
COPY --from=slack-tools /usr/local/bin/slack /usr/local/bin/slack-mcp /usr/local/bin/
COPY --from=slack-tools /opt/slackcli /opt/slackcli
COPY --from=gauge-tools /usr/local/bin/gcx /usr/local/bin/mcp-grafana /usr/local/bin/
COPY --from=gauge-tools /opt/gaugecli /opt/gaugecli
RUN chmod +x /usr/local/bin/linear /usr/local/bin/jira /usr/local/bin/slack \
             /usr/local/bin/slack-mcp /usr/local/bin/gcx /usr/local/bin/mcp-grafana

ARG APEX_TASK=Observability/containers-podman-compose-2-1238-observability
RUN python - <<PY
from huggingface_hub import snapshot_download
snapshot_download(repo_id="mercor/APEX-SWE", repo_type="dataset",
                  allow_patterns=["${APEX_TASK}/repo/**"], local_dir="/tmp/apex")
PY
RUN mkdir -p /app && cp -a "/tmp/apex/${APEX_TASK}/repo" /app/repo && rm -rf /tmp/apex
WORKDIR /app/repo
RUN pip install --no-cache-dir cython numpy setuptools wheel 2>/dev/null || true
RUN pip install --no-cache-dir -r requirements.txt 2>/dev/null || true
RUN pip install --no-cache-dir -r test-requirements.txt 2>/dev/null || true
RUN pip install --no-cache-dir pytest 2>/dev/null || true
RUN git init -q && git config user.email agent@example.local && git config user.name "Agent User" \
 && git add -A && git commit -q -m "snapshot" || true

ENV PYTHONPATH=/opt:/opt/ticketvector:/opt/slackcli:/opt/gaugecli \
    WORLD_ISSUES_BACKEND=remote \
    WORLD_ISSUES_OUTPUT=json \
    WORLD_ISSUES_AGENT_MODE=1 \
    WORLD_ISSUES_ACTOR=agent \
    WORLD_ISSUES_DEFAULT_PROJECT=PODMAN \
    PLANE_BASE_URL=http://127.0.0.1:8765 \
    SLACK_API_URL=http://slack \
    SLACK_BOT_TOKEN=test-token-meridian-eval \
    GRAFANA_URL=http://gauge \
    GRAFANA_TOKEN=test-token-meridian-eval \
    GRAFANA_SERVICE_ACCOUNT_TOKEN=test-token-meridian-eval
WORKDIR /app/repo
CMD ["sleep", "infinity"]

# Agent container (the Harbor `main` service) — the ONLY thing built per task, and deliberately
# THIN: a clean python base + the codebase, so the agent container carries zero Mattermost/gateway
# tells (this is what preserves realism). The heavy backend is the prebuilt `slack-service` image,
# pulled (not built) for the `api` service. Tools: curl + the official slack_sdk (Slack Web API via
# SLACK_API_URL / SLACK_BOT_TOKEN env), python+pytest. The backend is the neutral host `api`;
# Mattermost, its port, /api/v4, and its headers are never visible.
FROM python:3.12-slim
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl jq git ca-certificates bash && \
    rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir slack_sdk pytest

ENV SLACK_API_URL=http://api \
    SLACK_BOT_TOKEN=xoxb-acme-eval-0001

COPY main-entrypoint.sh /usr/local/bin/main-entrypoint.sh
RUN chmod +x /usr/local/bin/main-entrypoint.sh

# The codebase the agent works on.
COPY codebase /workspace
WORKDIR /workspace
ENTRYPOINT ["/usr/local/bin/main-entrypoint.sh"]

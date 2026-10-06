FROM ghcr.io/abundant-ai/ghc-service:latest@sha256:d4e88d7fa4af0ae84213d54f4b884b3a8954ebad9fe88b6f6fb97cea1443b3cf AS gh-tools
FROM ghcr.io/abundant-ai/ticketvector-service:main@sha256:9a3feabe3d493adec7c678d6e89b92fd3b65ac05cc788fae97b4fcf674fb4f42 AS ticketvector-tools
FROM ghcr.io/abundant-ai/slack-service:latest@sha256:64479855b91ec9bf3af9bccda92e76764ba71f27c6f64a98caeec57379a4afd7

USER root
RUN id agent >/dev/null 2>&1 || useradd --create-home --shell /bin/bash agent
COPY --from=gh-tools /usr/local/bin/gh /usr/local/bin/ghc /usr/local/bin/
COPY --from=gh-tools /opt/ghclone /opt/ghclone
COPY --from=gh-tools /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.10/dist-packages
COPY shared/payment-retry-policy/app-src /app/src
COPY --from=ticketvector-tools /usr/local/bin/linear /usr/local/bin/jira /usr/local/bin/
COPY --from=ticketvector-tools /opt/ticketvector /opt/ticketvector
RUN ln -sf "$(command -v python3)" /usr/local/bin/python && \
    chmod +x /usr/local/bin/gh /usr/local/bin/ghc /usr/local/bin/linear /usr/local/bin/jira /usr/local/bin/slack /usr/local/bin/slack-mcp && \
    mkdir -p /app/artifacts && \
    mkdir -p /var/lib/ticketvector && chmod 700 /var/lib/ticketvector && \
    git -C /app/src init && \
    git -C /app/src config user.email agent@example.local && \
    git -C /app/src config user.name "Agent User" && \
    git -C /app/src add . && \
    GIT_AUTHOR_DATE="2026-06-07T12:00:00Z" GIT_COMMITTER_DATE="2026-06-07T12:00:00Z" git -C /app/src commit -m "Initial task snapshot" && \
    git -C /app/src remote add origin http://github/acme/payment-retry-policy.git && \
    chown -R root:root /opt/ghclone /opt/ticketvector /opt/slackcli /var/lib/ticketvector && \
    chown -R agent:agent /app/src /app/artifacts
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*
WORKDIR /app/src
USER agent
ENV GH_HOST=http://github \
    GH_TOKEN_FILE=/run/secrets/token \
    WORLD_ISSUES_AGENT_MODE=1 \
    WORLD_ISSUES_BACKEND=remote \
    WORLD_ISSUES_OUTPUT=json \
    WORLD_ISSUES_ACTOR=agent \
    PLANE_BASE_URL=http://127.0.0.1:8765 \
    PYTHONPATH=/opt:/opt/ticketvector:/opt/slackcli:${PYTHONPATH} \
    SLACK_API_URL=http://slack \
    SLACK_BOT_TOKEN=test-token-acme-eval
CMD ["sleep", "infinity"]

FROM ghcr.io/abundant-ai/ghc-service:latest AS gh-tools
FROM ghcr.io/abundant-ai/ticketvector-service:main AS ticketvector-tools
FROM ghcr.io/abundant-ai/slack-service:latest

USER root
RUN id agent >/dev/null 2>&1 || useradd --create-home --shell /bin/bash agent
COPY --from=gh-tools /usr/local/bin/gh /usr/local/bin/ghc /usr/local/bin/
COPY --from=gh-tools /opt/ghclone /opt/ghclone
COPY --from=gh-tools /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.10/dist-packages
COPY --from=ticketvector-tools /usr/local/bin/linear /usr/local/bin/jira /usr/local/bin/
COPY --from=ticketvector-tools /opt/ticketvector /opt/ticketvector
RUN ln -sf "$(command -v python3)" /usr/local/bin/python && \
    chmod +x /usr/local/bin/gh /usr/local/bin/ghc /usr/local/bin/linear /usr/local/bin/jira /usr/local/bin/slack /usr/local/bin/slack-mcp && \
    mkdir -p /app && \
    mkdir -p /var/lib/ticketvector && chmod 700 /var/lib/ticketvector && \
    chown -R root:root /opt/ghclone /opt/ticketvector /opt/slackcli /var/lib/ticketvector && \
    chown -R agent:agent /app
WORKDIR /app
USER agent
ENV GH_HOST=http://github \
    GH_TOKEN_FILE=/run/secrets/token \
    WORLD_ISSUES_AGENT_MODE=1 \
    WORLD_ISSUES_BACKEND=remote \
    WORLD_ISSUES_OUTPUT=json \
    WORLD_ISSUES_ACTOR=agent \
    PLANE_BASE_URL=http://127.0.0.1:8765 \
    PYTHONPATH=/opt:/opt/ticketvector:/opt/slackcli \
    SLACK_API_URL=http://slack \
    SLACK_BOT_TOKEN=test-token-acme-eval
CMD ["sleep", "infinity"]

# Agent (`main`) container. Pure retrieval task: no buggy SUT, the agent just fetches
# basic facts from five clones and writes them to a file. We layer every clone's CLI in
# from its service image so the agent reaches each backend ONLY over HTTP via its tool:
#   * slack  — slack CLI            (http://slack)        from slack-service
#   * jira   — linear/jira CLI      (http://jira:8765)    from ticketvector-service
#   * github — gh / ghc CLI         (http://github)       from ghc-service
#   * gauge  — gcx CLI              (http://gauge)        from gauge-service
#   * sentry — sentry CLI          (http://sentry)       from sentry-clone-service
# No seed data rides along on disk — it lives only behind each service.
FROM ghcr.io/abundant-ai/slack-service:slack-mcp-oss AS slack-tools
FROM ghcr.io/abundant-ai/ticketvector-service:main AS tv-tools
FROM ghcr.io/abundant-ai/ghc-service:latest AS gh-tools
FROM ghcr.io/abundant-ai/gauge-service:main AS gauge-tools
FROM ghcr.io/abundant-ai/sentry-clone-service:main AS sentry-tools

FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl jq git ca-certificates bash \
    && pip install --no-cache-dir "slack_sdk>=3.27" pytest \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Clone CLIs + their support packages.
COPY --from=slack-tools /usr/local/bin/slack /usr/local/bin/slack-mcp /usr/local/bin/
COPY --from=slack-tools /opt/slackcli /opt/slackcli
COPY --from=tv-tools /usr/local/bin/linear /usr/local/bin/jira /usr/local/bin/
COPY --from=tv-tools /opt/ticketvector /opt/ticketvector
COPY --from=gh-tools /usr/local/bin/gh /usr/local/bin/ghc /usr/local/bin/
COPY --from=gh-tools /opt/ghclone /opt/ghclone
COPY --from=gauge-tools /usr/local/bin/gcx /usr/local/bin/mcp-grafana /usr/local/bin/
COPY --from=gauge-tools /opt/gaugecli /opt/gaugecli
COPY --from=sentry-tools /usr/local/bin/sentry /usr/local/bin/sentry-mcp /usr/local/bin/
COPY --from=sentry-tools /opt/sentry-clone-cli /opt/sentry-clone-cli

RUN chmod +x /usr/local/bin/slack /usr/local/bin/slack-mcp /usr/local/bin/linear \
             /usr/local/bin/jira /usr/local/bin/gh /usr/local/bin/ghc /usr/local/bin/gcx \
             /usr/local/bin/mcp-grafana /usr/local/bin/sentry /usr/local/bin/sentry-mcp 2>/dev/null || true
RUN ln -sf "$(command -v python3)" /usr/local/bin/python 2>/dev/null || true

COPY codebase /app
WORKDIR /app

ENV PYTHONPATH=/opt:/opt/slackcli:/opt/ticketvector:/opt/ghclone:/opt/gaugecli:/opt/sentry-clone-cli \
    SLACK_API_URL=http://slack \
    SLACK_BOT_TOKEN=xoxp-acme-eval-0001 \
    PLANE_BASE_URL=http://jira:8765 \
    PLANE_API_KEY=test-token-acme-eval \
    WORLD_ISSUES_BACKEND=remote \
    WORLD_ISSUES_AGENT_MODE=1 \
    WORLD_ISSUES_OUTPUT=json \
    WORLD_ISSUES_ACTOR=agent \
    WORLD_ISSUES_DEFAULT_PROJECT=WEB \
    GH_HOST=http://github \
    GH_TOKEN_FILE=/run/secrets/token \
    GRAFANA_URL=http://gauge \
    GRAFANA_TOKEN=test-token-acme-eval \
    GRAFANA_SERVICE_ACCOUNT_TOKEN=test-token-acme-eval \
    SENTRY_URL=http://sentry \
    SENTRY_AUTH_TOKEN=test-token-acme-eval \
    SENTRY_ORG=acme

# `main` is just the agent box — don't inherit any service entrypoint.
ENTRYPOINT []
CMD ["sleep", "infinity"]

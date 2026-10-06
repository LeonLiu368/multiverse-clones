# Agent container (Harbor `main`), built FROM the prebuilt slack-service image (SQLite Slack gateway
# + importer + `slack` CLI + korotovsky `slack-mcp` + pytest). This layer bakes in BOTH the seed
# export and the codebase, so the task is fully self-contained — no runtime volume mount needed.
#
# Pinned to the branch-scoped image ghcr.io/abundant-ai/slack-service:slack-mcp-oss (public), so this
# experiment does not depend on (or clobber) the shared :latest.
FROM ghcr.io/abundant-ai/slack-service:slack-mcp-oss

ENV SLACK_API_URL=http://localhost \
    SLACK_BOT_TOKEN=xoxp-acme-eval-0001

COPY main-entrypoint.sh /usr/local/bin/main-entrypoint.sh
RUN chmod +x /usr/local/bin/main-entrypoint.sh

# Bake the seed (a real Slack export) + the codebase into the image.
COPY data/slack-export /data/slack-export
COPY codebase /workspace
WORKDIR /workspace
ENTRYPOINT ["/usr/local/bin/main-entrypoint.sh"]

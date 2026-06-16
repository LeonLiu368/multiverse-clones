# Agent container (Harbor `main`) for the FULL real Slack export (88 channels, 2.4M messages).
# Pulls the pre-built DB from the versioned seed image — no data committed, no import at boot.
FROM ghcr.io/abundant-ai/slack-service:slack-mcp-oss
ENV SLACK_API_URL=http://localhost \
    SLACK_BOT_TOKEN=xoxp-acme-eval-0001
COPY --from=ghcr.io/abundant-ai/slack-seed:full /slack.prebuilt.db /opt/slack.prebuilt.db
COPY main-entrypoint.sh /usr/local/bin/main-entrypoint.sh
RUN chmod +x /usr/local/bin/main-entrypoint.sh
COPY codebase /workspace
WORKDIR /workspace
ENTRYPOINT ["/usr/local/bin/main-entrypoint.sh"]

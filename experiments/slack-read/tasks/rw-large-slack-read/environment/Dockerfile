# Agent container (Harbor `main`). Pulls a PRE-BUILT SQLite DB from a versioned seed image instead
# of carrying the raw export — so the real-world Slack data lives in ghcr.io/abundant-ai/slack-seed,
# not in this task. Boot uses the baked DB directly (slack-boot.sh skips import). Self-contained.
FROM ghcr.io/abundant-ai/slack-service:slack-mcp-oss

ENV SLACK_API_URL=http://localhost \
    SLACK_BOT_TOKEN=xoxp-acme-eval-0001

# The seed: a tiny image carrying just /slack.prebuilt.db for the eng-2021q1 export.
COPY --from=ghcr.io/abundant-ai/slack-seed:eng-2021q1 /slack.prebuilt.db /opt/slack.prebuilt.db

COPY main-entrypoint.sh /usr/local/bin/main-entrypoint.sh
RUN chmod +x /usr/local/bin/main-entrypoint.sh
COPY codebase /workspace
WORKDIR /workspace
ENTRYPOINT ["/usr/local/bin/main-entrypoint.sh"]

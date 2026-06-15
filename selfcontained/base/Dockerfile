# Agent container (Harbor `main`) — built per task FROM the prebuilt slack-service image.
# The service image already contains the SQLite-backed Slack gateway + seeder/importer + agent
# tools (our `slack` CLI, the korotovsky `slack-mcp` server, pytest). This layer adds the codebase.
#
# BRANCH-ISOLATED TAG: this `slack-mcp-oss` branch builds against the branch-scoped image so it does
# NOT depend on (or clobber) the shared `:latest`. CI pushes `slack-service:slack-mcp-oss` for this
# branch. >>> On merge to main, change this back to `:latest` (CI publishes `:latest` from main). <<<
FROM ghcr.io/abundant-ai/slack-service:slack-mcp-oss

# Gateway runs on localhost (same container as the agent).
ENV SLACK_API_URL=http://localhost \
    SLACK_BOT_TOKEN=xoxp-acme-eval-0001

COPY main-entrypoint.sh /usr/local/bin/main-entrypoint.sh
RUN chmod +x /usr/local/bin/main-entrypoint.sh

# The codebase the agent works on.
COPY codebase /workspace
WORKDIR /workspace
ENTRYPOINT ["/usr/local/bin/main-entrypoint.sh"]

# Agent container (Harbor `main`) — built per task FROM the prebuilt slack-service image.
# The service image already contains the SQLite-backed Slack gateway + seeder/importer + agent
# tools (our `slack` CLI, the korotovsky `slack-mcp` server, pytest). This layer adds the codebase.
FROM ghcr.io/abundant-ai/slack-service:latest

# Gateway runs on localhost (same container as the agent).
ENV SLACK_API_URL=http://localhost \
    SLACK_BOT_TOKEN=xoxp-acme-eval-0001

COPY main-entrypoint.sh /usr/local/bin/main-entrypoint.sh
RUN chmod +x /usr/local/bin/main-entrypoint.sh

# The codebase the agent works on.
COPY codebase /workspace
WORKDIR /workspace
ENTRYPOINT ["/usr/local/bin/main-entrypoint.sh"]

# Agent (`main`) container — Harbor builds this automatically as the agent's image.
# It ships ONLY the agent's tools (slack-cli + the slack-mcp MCP server), both thin
# clients of the slack service at $SLACK_API_URL. No seed data, no DB: the agent can
# reach the workspace only through these tools.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl jq \
    && rm -rf /var/lib/apt/lists/*

# vendored package (code only) -> provides `slack-cli` and `slack-mcp`
COPY slackclone /opt/slackclone
RUN pip install --no-cache-dir "/opt/slackclone[mcp]"

ENV SLACK_API_URL=http://slack:3000
WORKDIR /app

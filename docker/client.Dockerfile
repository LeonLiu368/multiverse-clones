# Slack-clone CLIENT image (the agent's `client` container). Build context = repo root:
#   docker build -f docker/client.Dockerfile -t abundant-slack-client:latest .
#
# Ships the agent's tools — `slack-cli` AND the `slack-mcp` MCP server — both of
# which are thin clients of the service at $SLACK_API_URL. NO seed data and NO
# control token: the agent can reach the workspace only through these tools.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl jq \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir ".[mcp]"   # provides `slack-cli` + `slack-mcp`

# Sample MCP server registration (stdio). An agent harness can point its MCP
# client at this file, or just launch `slack-mcp` directly.
COPY docker/mcp.json /app/mcp.json

ENV SLACK_API_URL=http://slack:3000
CMD ["sleep", "infinity"]

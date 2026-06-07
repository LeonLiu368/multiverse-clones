# Agent container (Harbor `main`) — single-container design.
# Built per task FROM the prebuilt slack-service image (Mattermost + gateway + seeder),
# then adds the agent tools (slack CLI + MCP) and the task codebase on top.
# Harbor force-builds `main` from this Dockerfile; the base image is pulled from GHCR.
FROM ghcr.io/abundant-ai/slack-service:latest

# Add git (not in the service base image) for agent use.
RUN apt-get update && \
    apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*

# Add the agent's Slack tools: the `slack` CLI + `slack-mcp` MCP server.
# The service image already has PYTHONPATH=/opt, so slackcli is importable directly
# from /opt/slackcli. We install its deps explicitly and write wrapper scripts for the
# CLI entry points (avoids pip/setuptools version issues on the Debian base).
COPY slackcli /opt/slackcli
RUN pip3 install --no-cache-dir "slack_sdk>=3.27" "mcp>=1.2" pytest && \
    printf '#!/usr/bin/env python3\nfrom slackcli.cli import main\nmain()\n' \
        > /usr/local/bin/slack && \
    printf '#!/usr/bin/env python3\nfrom slackcli.mcp_server import main\nmain()\n' \
        > /usr/local/bin/slack-mcp && \
    chmod +x /usr/local/bin/slack /usr/local/bin/slack-mcp

# Gateway runs on localhost (same container as the agent).
# Extend PYTHONPATH so slackcli (at /opt/slackcli/slackcli/) is importable as `slackcli`.
# (The service image sets PYTHONPATH=/opt; /opt/slackcli is the project root, not the package.)
ENV SLACK_API_URL=http://localhost \
    SLACK_BOT_TOKEN=xoxb-acme-eval-0001 \
    PYTHONPATH=/opt:/opt/slackcli

COPY main-entrypoint.sh /usr/local/bin/main-entrypoint.sh
RUN chmod +x /usr/local/bin/main-entrypoint.sh

# The codebase the agent works on.
COPY codebase /workspace
WORKDIR /workspace
ENTRYPOINT ["/usr/local/bin/main-entrypoint.sh"]

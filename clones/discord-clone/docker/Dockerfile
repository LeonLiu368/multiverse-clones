# The single, pullable discord-service base image (R2.a).
#
# Contains the Discord REST API server PLUS the agent's thin clients (the `discord`
# CLI and `discord-mcp`) — but NO task data. A task provides data per task, either by
# mounting a fixture.json into THIS container (DISCORD_FIXTURE) or pushing it through
# the token-gated /_control/seed plane. Built once and published to GHCR; tasks pull
# it as their `discord` service. `:empty` and `:prod-v1` both FROM this base.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl jq \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/discordclone
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir ".[mcp]"

COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Defaults; a task overrides DISCORD_FIXTURE (mounted at runtime) or seeds via control plane.
ENV DISCORD_DB=/srv/discord.db \
    DISCORD_FIXTURE=/srv/fixture.json \
    PORT=8080
EXPOSE 8080

# NB: do NOT set DISCORD_CONTROL_TOKEN here — leaving it unset keeps /_control/* disabled (404).
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

# The single, pullable notion-service base image (R2.a).
#
# Contains the Notion REST API server PLUS the agent's thin clients (notion-cli and
# notion-mcp) — but NO task data. A task provides data per task, either by mounting
# a fixture.json into THIS container (NOTION_FIXTURE) or pushing it through the
# token-gated /_control/seed plane. Built once and published to GHCR; tasks pull it
# as their `notion` service. `:empty` and `:prod-v1` both FROM this base.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl jq \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/notionclone
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir ".[mcp]"

COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Defaults; a task overrides NOTION_FIXTURE (mounted at runtime) or seeds via control plane.
ENV NOTION_DB=/srv/notion.db \
    NOTION_FIXTURE=/srv/fixture.json \
    PORT=3000
EXPOSE 3000

# NB: do NOT set NOTION_CONTROL_TOKEN here — leaving it unset keeps /_control/* disabled (404).
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

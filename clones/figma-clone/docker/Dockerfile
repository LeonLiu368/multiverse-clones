# The single, pullable figma-service image.
#
# It contains the Figma REST API server PLUS the agent's thin clients (figma-cli
# and figma-mcp) — but NO task data. A task provides its design data per task,
# either by mounting a fixture.json into THIS container (FIGMA_FIXTURE) or by
# pushing it through the token-gated /_control/seed plane. Built once and pushed
# to a registry; tasks pull it as their `figma` service.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl jq \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/figmaclone
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir ".[mcp]"

COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Defaults; a task overrides FIGMA_FIXTURE (mounted at runtime) or seeds via control plane.
ENV FIGMA_DB=/srv/figma.db \
    FIGMA_FIXTURE=/srv/fixture.json \
    PORT=3000
EXPOSE 3000
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

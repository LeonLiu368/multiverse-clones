# The `figma` service image, built self-contained from the task's environment/ dir
# (the vendored figmaclone package). Built locally by `docker compose build` so the
# task needs no registry auth; compose tags it as the image name in the compose
# file. It is identical in behavior to the published ghcr.io/leonliu368/figma-service
# image: the Figma REST API + figma-cli + figma-mcp, with NO task data baked in —
# the design data is mounted per task as /srv/fixture.json (service container only).
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl jq \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/figmaclone
COPY figmaclone/pyproject.toml figmaclone/README.md ./
COPY figmaclone/src ./src
RUN pip install --no-cache-dir ".[mcp]"

COPY figma.entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

ENV FIGMA_DB=/srv/figma.db \
    FIGMA_FIXTURE=/srv/fixture.json \
    PORT=3000
EXPOSE 3000
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

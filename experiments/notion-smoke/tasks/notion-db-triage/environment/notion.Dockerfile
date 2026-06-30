# The `notion` gateway service for this task — equivalent to notion-service:prod-v1.
#
# Builds the notion-service base from the vendored package, then bakes the corpus DB
# so it serves the full workspace mount-free (the GHCR image-DB-seeding path, R2.j).
# The compose `image:` name matches the published ghcr.io/abundant-ai/notion-service
# :prod-v1, so a pull works too; the `build:` is the no-creds local fallback (R1.5).
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl jq \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/notionclone
COPY notionclone/pyproject.toml notionclone/README.md ./
COPY notionclone/src ./src
RUN pip install --no-cache-dir ".[mcp]"

COPY notionclone/docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Bake the corpus -> served as-is, no mount, no seeding (R2.j).
COPY notion_corpus.db /srv/notion.db
ENV NOTION_DB=/srv/notion.db \
    PORT=3000
EXPOSE 3000
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

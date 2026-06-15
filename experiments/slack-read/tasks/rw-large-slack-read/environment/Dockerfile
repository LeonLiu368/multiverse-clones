# Agent container (Harbor `main`), built FROM the prebuilt slack-service image (SQLite Slack gateway
# + importer + `slack` CLI + korotovsky `slack-mcp` + pytest). This layer bakes in the seed export,
# PRE-BUILDS the SQLite DB at docker-build time (so boot is instant — no per-container import), and
# adds the placeholder codebase. Fully self-contained — no runtime mount.
#
# Pinned to the branch-scoped image ghcr.io/abundant-ai/slack-service:slack-mcp-oss (public), so this
# experiment does not depend on (or clobber) the shared :latest.
FROM ghcr.io/abundant-ai/slack-service:slack-mcp-oss

ENV SLACK_API_URL=http://localhost \
    SLACK_BOT_TOKEN=xoxp-acme-eval-0001

COPY main-entrypoint.sh /usr/local/bin/main-entrypoint.sh
RUN chmod +x /usr/local/bin/main-entrypoint.sh

# Bake the real Slack export, then pre-build the SQLite DB from it at build time.
COPY data/slack-export /data/slack-export
RUN python3 /opt/import_export.py --export-dir /data/slack-export --db /opt/slack.prebuilt.db

COPY codebase /workspace
WORKDIR /workspace
ENTRYPOINT ["/usr/local/bin/main-entrypoint.sh"]

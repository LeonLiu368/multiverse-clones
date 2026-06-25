# Bake a spoink-captured Slack export into a slack-gateway image (deployed family).
#
# Build context must contain ./export = a standard Slack export dir
# (users.json, channels.json, <channel>/YYYY-MM-DD.json). The gateway's OWN
# /opt/import_export.py pre-builds the SQLite DB at /opt/slack.prebuilt.db at
# build time, so boot is instant (slack-boot.sh copies the prebuilt db) and the
# image drops into the existing task setup unchanged (Slack Web API on :80).
ARG BASE=ghcr.io/abundant-ai/slack-gateway:empty
FROM ${BASE}
COPY export /tmp/build-export
RUN python3 /opt/import_export.py --export-dir /tmp/build-export --db /opt/slack.prebuilt.db \
 && rm -rf /tmp/build-export

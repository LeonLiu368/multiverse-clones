#!/bin/sh
# Seed the SQLite db once from the baked-in workspace, then serve the Slack API.
set -e
DB="${SLACK_DB:-/srv/slack.db}"

if [ ! -f "$DB" ]; then
  if [ -f /srv/workspace.json ]; then
    echo "[entrypoint] seeding from /srv/workspace.json"
    slack-cli seed load /srv/workspace.json --out "$DB"
  else
    echo "[entrypoint] no workspace baked in; generating synthetic"
    slack-cli seed generate --out "$DB"
  fi
fi

echo "[entrypoint] serving on :${PORT:-3000}"
exec uvicorn slackclone.api.app:app --host 0.0.0.0 --port "${PORT:-3000}"

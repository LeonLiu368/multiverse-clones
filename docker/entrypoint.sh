#!/bin/sh
# Seed the SQLite db from a mounted source (once), then serve the Slack API.
# Seed source priority under $SLACK_SEED_DIR (default /data/slack):
#   slack.db        -> used as-is
#   workspace.json  -> `slack-cli seed load`
#   export/         -> `slack-cli seed import-export` (real Slack export dir)
# If nothing is mounted, a deterministic synthetic workspace is generated.
set -e

DB="${SLACK_DB:-/srv/slack.db}"
DATA="${SLACK_SEED_DIR:-/data/slack}"

if [ ! -f "$DB" ]; then
  if [ -f "$DATA/slack.db" ]; then
    echo "[entrypoint] using prebuilt $DATA/slack.db"
    cp "$DATA/slack.db" "$DB"
  elif [ -f "$DATA/workspace.json" ]; then
    echo "[entrypoint] seeding from $DATA/workspace.json"
    slack-cli seed load "$DATA/workspace.json" --out "$DB"
  elif [ -d "$DATA/export" ]; then
    echo "[entrypoint] importing Slack export $DATA/export"
    slack-cli seed import-export "$DATA/export" --out "$DB"
  else
    echo "[entrypoint] no seed under $DATA; generating synthetic workspace"
    slack-cli seed generate --out "$DB"
  fi
fi

echo "[entrypoint] serving on :${PORT:-3000}"
exec uvicorn slackclone.api.app:app --host 0.0.0.0 --port "${PORT:-3000}"

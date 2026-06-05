#!/bin/sh
# Seed the SQLite db once, then serve the Slack API.
#
# Seed selection order (first match wins):
#   1. $SLACK_WORKSPACE set + catalog file exists -> load the baked workspace by name
#        (the canonical path; data lives in the image, never in a task dir)
#   2. mounted $SLACK_SEED_DIR (default /data/slack) escape hatch:
#        slack.db -> as-is | workspace.json -> seed load | export/ -> import-export
#   3. $SLACK_WORKSPACE set but NOT in the catalog -> fail loud (don't serve a
#        silently-wrong / empty workspace)
#   4. nothing specified -> deterministic synthetic workspace
set -e

DB="${SLACK_DB:-/srv/slack.db}"
DATA="${SLACK_SEED_DIR:-/data/slack}"
WSDIR="${SLACK_WORKSPACE_DIR:-/srv/workspaces}"
WS="${SLACK_WORKSPACE:-}"

if [ ! -f "$DB" ]; then
  if [ -n "$WS" ] && [ -f "$WSDIR/$WS.json" ]; then
    echo "[entrypoint] seeding workspace '$WS' from catalog $WSDIR"
    slack-cli seed load "$WSDIR/$WS.json" --out "$DB"
  elif [ -f "$DATA/slack.db" ]; then
    echo "[entrypoint] using prebuilt $DATA/slack.db"
    cp "$DATA/slack.db" "$DB"
  elif [ -f "$DATA/workspace.json" ]; then
    echo "[entrypoint] seeding from $DATA/workspace.json"
    slack-cli seed load "$DATA/workspace.json" --out "$DB"
  elif [ -d "$DATA/export" ]; then
    echo "[entrypoint] importing Slack export $DATA/export"
    slack-cli seed import-export "$DATA/export" --out "$DB"
  elif [ -n "$WS" ]; then
    echo "[entrypoint] ERROR: SLACK_WORKSPACE='$WS' not found in catalog $WSDIR" >&2
    echo "[entrypoint] available: $(ls "$WSDIR" 2>/dev/null | sed 's/\.json$//' | tr '\n' ' ')" >&2
    exit 1
  else
    echo "[entrypoint] no workspace specified; generating synthetic workspace"
    slack-cli seed generate --out "$DB"
  fi
fi

echo "[entrypoint] serving on :${PORT:-3000}"
exec uvicorn slackclone.api.app:app --host 0.0.0.0 --port "${PORT:-3000}"

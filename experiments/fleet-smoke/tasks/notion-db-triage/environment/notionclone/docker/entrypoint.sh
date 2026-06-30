#!/bin/sh
# Seed the SQLite db once, then serve the Notion REST API.
#
# Data comes from ONE of (in priority order):
#   1. An existing $NOTION_DB already present (the baked :prod-v1 corpus) → serve
#      as-is, no seeding, no mount required.
#   2. A canonical-seed fixture mounted at $NOTION_FIXTURE (default /srv/fixture.json)
#      → load it. Mount it into THIS service container only, never the agent.
#   3. A named synthetic workspace via $NOTION_WORKSPACE (deterministic) → generate.
#   4. Otherwise start empty and wait for an operator to POST /_control/seed
#      (requires NOTION_CONTROL_TOKEN; the agent never gets that token).
set -e
DB="${NOTION_DB:-/srv/notion.db}"
FIXTURE="${NOTION_FIXTURE:-/srv/fixture.json}"
WS="${NOTION_WORKSPACE:-}"

if [ ! -f "$DB" ]; then
  if [ -f "$FIXTURE" ]; then
    echo "[entrypoint] seeding from $FIXTURE"
    notion-cli seed load "$FIXTURE" --out "$DB"
  elif [ -n "$WS" ]; then
    echo "[entrypoint] generating synthetic workspace '$WS'"
    notion-cli seed generate --workspace "$WS" --out "$DB"
  else
    echo "[entrypoint] no fixture at $FIXTURE; starting empty (seed via /_control/seed)"
  fi
else
  echo "[entrypoint] serving existing $DB as-is (no seeding)"
fi

echo "[entrypoint] serving notion-clone on :${PORT:-3000}"
exec uvicorn notionclone.api.app:app --host 0.0.0.0 --port "${PORT:-3000}"

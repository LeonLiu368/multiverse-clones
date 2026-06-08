#!/bin/sh
# Seed the SQLite db once, then serve the Figma REST API.
#
# Data comes from ONE of (in order):
#   1. A canonical-seed fixture mounted at $FIGMA_FIXTURE (default /srv/fixture.json).
#      Mount it into THIS service container only — never the agent container — so
#      the seeded spec is reachable solely through the API.
#   2. Otherwise, start empty and wait for an operator to POST /_control/seed
#      (requires FIGMA_CONTROL_TOKEN; the agent never gets that token).
set -e
DB="${FIGMA_DB:-/srv/figma.db}"
FIXTURE="${FIGMA_FIXTURE:-/srv/fixture.json}"

if [ ! -f "$DB" ]; then
  if [ -f "$FIXTURE" ]; then
    echo "[entrypoint] seeding from $FIXTURE"
    figma-cli seed load "$FIXTURE" --out "$DB"
  else
    echo "[entrypoint] no fixture at $FIXTURE; starting empty (seed via /_control/seed)"
  fi
fi

echo "[entrypoint] serving figma-clone on :${PORT:-3000}"
exec uvicorn figmaclone.api.app:app --host 0.0.0.0 --port "${PORT:-3000}"

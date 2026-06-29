#!/bin/sh
# Seed the SQLite db once from the mounted fixture, then serve the Figma REST API.
# The fixture is mounted into THIS service container only (never `main`), so the
# seeded spec is reachable solely through the API.
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

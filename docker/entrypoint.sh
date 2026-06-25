#!/bin/sh
# Seed the SQLite db once from the mounted fixture (service container only), then serve.
set -e
DB="${GWS_DB:-/srv/gws.db}"
FIXTURE="${GWS_FIXTURE:-/srv/fixture.json}"

if [ ! -f "$DB" ]; then
  if [ -f "$FIXTURE" ]; then
    echo "[entrypoint] seeding from $FIXTURE"
    gws-cli seed load "$FIXTURE" --out "$DB"
  else
    echo "[entrypoint] no fixture at $FIXTURE; starting empty (seed via /_control/seed)"
  fi
fi

echo "[entrypoint] serving gworkspace-clone on :${PORT:-8080}"
exec uvicorn gwsclone.api.app:app --host 0.0.0.0 --port "${PORT:-8080}"

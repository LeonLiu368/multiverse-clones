#!/bin/sh
# Seed the SQLite db once, then serve the Discord REST API.
#
# Data comes from ONE of (in priority order):
#   1. An existing $DISCORD_DB already present (the baked :prod-v1 corpus) → serve
#      as-is, no seeding, no mount required.
#   2. A canonical-seed fixture mounted at $DISCORD_FIXTURE (default /srv/fixture.json)
#      → load it. Mount it into THIS service container only, never the agent.
#   3. A named synthetic guild via $DISCORD_GUILD (deterministic) → generate.
#   4. Otherwise start empty and wait for an operator to POST /_control/seed
#      (requires DISCORD_CONTROL_TOKEN; the agent never gets that token).
set -e
DB="${DISCORD_DB:-/srv/discord.db}"
FIXTURE="${DISCORD_FIXTURE:-/srv/fixture.json}"
GUILD="${DISCORD_GUILD:-}"

if [ ! -f "$DB" ]; then
  if [ -f "$FIXTURE" ]; then
    echo "[entrypoint] seeding from $FIXTURE"
    discord seed load "$FIXTURE" --out "$DB"
  elif [ -n "$GUILD" ]; then
    echo "[entrypoint] generating synthetic guild '$GUILD'"
    discord seed generate --guild "$GUILD" --out "$DB"
  else
    echo "[entrypoint] no fixture at $FIXTURE; starting empty (seed via /_control/seed)"
  fi
else
  echo "[entrypoint] serving existing $DB as-is (no seeding)"
fi

echo "[entrypoint] serving discord-clone on :${PORT:-8080}"
exec uvicorn discordclone.api.app:app --host 0.0.0.0 --port "${PORT:-8080}"

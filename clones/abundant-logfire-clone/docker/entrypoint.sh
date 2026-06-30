#!/bin/sh
# Gateway entrypoint. Two seeding paths, selected by what's on disk:
#   * :prod-v1  -> a corpus is BAKED at $LOGFIRE_BAKED (records.json[.gz]); served as-is,
#                  any per-task mount is ignored.
#   * :empty    -> no baked corpus; a per-task fixture is MOUNTED at $LOGFIRE_RECORDS.
# The server (logfire_clone.server) transparently gunzips a .gz corpus.
set -e
BAKED="${LOGFIRE_BAKED:-/data/records.json.gz}"
RECORDS="${LOGFIRE_RECORDS:-/data/records.json}"

if [ -f "$BAKED" ]; then
  echo "[entrypoint] serving BAKED corpus from $BAKED (mount ignored)"
  export LOGFIRE_RECORDS="$BAKED"
elif [ -f "$RECORDS" ] || [ -f "$RECORDS.gz" ]; then
  echo "[entrypoint] serving MOUNTED corpus from $RECORDS"
  export LOGFIRE_RECORDS="$RECORDS"
else
  echo "[entrypoint] FATAL: no corpus baked at $BAKED and none mounted at $RECORDS" >&2
  exit 1
fi

exec python -m logfire_clone.server

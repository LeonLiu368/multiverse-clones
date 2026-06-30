#!/usr/bin/env sh
# Gateway entrypoint for the sentry-clone service image trio.
#
#   :empty    — no data baked in. A per-task fixture is MOUNTED at
#               $SENTRY_CLONE_STATE_FILE (default /data/sentry-clone/state.json).
#               The server copies the seed to the runtime path and mutates the copy.
#   :prod-v1  — a corpus state.json is BAKED into the image at
#               $SENTRY_CLONE_CORPUS_FILE (/srv/sentry-clone/corpus-state.json). When
#               no fixture is mounted at $SENTRY_CLONE_STATE_FILE, the entrypoint serves
#               the baked corpus mount-free. Switching empty<->prod-v1 is the image tag
#               alone; a fixture mount on prod-v1 takes precedence if one is provided.
set -eu

SEED="${SENTRY_CLONE_STATE_FILE:-/data/sentry-clone/state.json}"
CORPUS="${SENTRY_CLONE_CORPUS_FILE:-/srv/sentry-clone/corpus-state.json}"

if [ ! -f "$SEED" ] && [ -f "$CORPUS" ]; then
  echo "[entrypoint] no fixture at $SEED; serving baked corpus $CORPUS (mount-free)" >&2
  export SENTRY_CLONE_STATE_FILE="$CORPUS"
elif [ -f "$SEED" ]; then
  echo "[entrypoint] serving seed $SEED" >&2
else
  echo "[entrypoint] WARNING: no fixture at $SEED and no baked corpus at $CORPUS" >&2
fi

exec python -m sentry_clone.server.app

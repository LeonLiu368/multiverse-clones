#!/usr/bin/env bash
# Boot the single-container Slack mock: import the seed (a real Slack export dir, or a legacy
# scraped.json) into SQLite, then start the gateway on :80. Shared by api-entrypoint.sh (service
# image run directly) and main-entrypoint.sh (the task `main` container). No Mattermost/Postgres.
set -uo pipefail

export SLACK_DB="${SLACK_DB:-/tmp/slack.db}"
PREBUILT="${SLACK_PREBUILT_DB:-/opt/slack.prebuilt.db}"
rm -f "$SLACK_DB"

# Fast path: a task image may PRE-BUILD the SQLite DB at docker-build time (running the importer in
# the Dockerfile) and bake it at $PREBUILT. If present, just copy it into place — boot is instant,
# regardless of dataset size, and the import cost is paid once at build instead of every container.
if [ -f "$PREBUILT" ]; then
  echo "[boot] using pre-built SQLite DB ($PREBUILT) — skipping import"
  cp "$PREBUILT" "$SLACK_DB"
  # Per-task OVERLAY: a task may mount/bake a small Slack export at /data/slack-overlay to layer its
  # own data on top of the shared prod corpus. import_export.py merges (INSERT OR REPLACE), so
  # overlay rows that reference a prod channel/user by name resolve to the same id and attach to it;
  # new channels/users/messages are added. Overlay timestamps should post-date the prod corpus so
  # (channel_id, ts) never collides. Harmless when absent.
  OVERLAY="${SLACK_OVERLAY_DIR:-/data/slack-overlay}"
  if [ -d "$OVERLAY" ] && [ -n "$(ls -A "$OVERLAY" 2>/dev/null)" ]; then
    echo "[boot] importing task overlay from $OVERLAY on top of the prod DB"
    python3 /opt/import_export.py --export-dir "$OVERLAY" --db "$SLACK_DB" --overlay || echo "[boot] overlay import error (non-fatal)"
  fi
# Otherwise import the seed at boot. Priority order:
#   1. a real Slack export directory at /data/slack-export (complete or anonymized variant)
#   2. a legacy scraped.json at /data/seed/scraped.json or /data/mattermost/scraped.json
elif [ -d /data/slack-export ] && [ -n "$(ls -A /data/slack-export 2>/dev/null)" ]; then
  echo "[boot] importing Slack export from /data/slack-export"
  python3 /opt/import_export.py --export-dir /data/slack-export --db "$SLACK_DB" || echo "[boot] import error (non-fatal)"
elif [ -f /data/seed/scraped.json ]; then
  echo "[boot] importing legacy scraped.json from /data/seed"
  python3 /opt/import_export.py --scraped /data/seed/scraped.json --db "$SLACK_DB" || echo "[boot] import error"
elif [ -f /data/mattermost/scraped.json ]; then
  echo "[boot] importing legacy scraped.json from /data/mattermost"
  python3 /opt/import_export.py --scraped /data/mattermost/scraped.json --db "$SLACK_DB" || echo "[boot] import error"
else
  echo "[boot] no seed found (empty workspace); creating schema"
  python3 -c "import sys; sys.path.insert(0,'/opt'); from slackgw.store import Store; Store('$SLACK_DB')"
fi

# Per-task PATCH: a task may mount/bake a JSON op-list that MUTATES the corpus (update/delete
# existing rows, beyond the additive overlay) at /data/slack-patch.json. Applied AFTER the
# seed/overlay import above, to whichever DB was built — prebuilt fast-path OR a boot-time import.
# Deliberately NOT guarded by `|| echo`: a patch whose `match` resolves to 0 or >1 rows must
# FAIL LOUD (apply_patch exits nonzero) and abort boot rather than silently shipping a wrong corpus.
PATCH="${SLACK_PATCH_FILE:-/data/slack-patch.json}"
if [ -f "$PATCH" ]; then
  echo "[boot] applying task patch from $PATCH"
  # No `set -e` in this script (and it's sourced), so check the status explicitly and abort boot on
  # an unresolved match — exit propagates out of the sourcing entrypoint and fails the container.
  if ! python3 /opt/import_export.py --db "$SLACK_DB" --patch "$PATCH"; then
    echo "[boot] FATAL: patch failed — aborting boot" >&2
    exit 1
  fi
fi

echo "[boot] starting Slack gateway on :80"
cd /opt
uvicorn slackgw.app:app --host 0.0.0.0 --port 80 --log-level warning --no-server-header &
GW_PID=$!

for _ in $(seq 1 30); do
  curl -s "http://localhost:80/api/auth.test" >/dev/null 2>&1 && break
  sleep 1
done

# Optional per-task hooks, run once the gateway is reachable (e.g. inject extra planted messages):
# the baked task-seed.sh (no-op by default) and an optional script a task drops in its data dir.
[ -x /usr/local/bin/task-seed.sh ] && bash /usr/local/bin/task-seed.sh || true
[ -f /data/seed/seed.sh ] && bash /data/seed/seed.sh || true

echo "[boot] gateway ready"
export GW_PID

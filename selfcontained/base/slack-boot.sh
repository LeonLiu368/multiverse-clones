#!/usr/bin/env bash
# Boot the single-container Slack mock: import the seed (a real Slack export dir, or a legacy
# scraped.json) into SQLite, then start the gateway on :80. Shared by api-entrypoint.sh (service
# image run directly) and main-entrypoint.sh (the task `main` container). No Mattermost/Postgres.
set -uo pipefail

export SLACK_DB="${SLACK_DB:-/tmp/slack.db}"
rm -f "$SLACK_DB"

# Seed source, in priority order:
#   1. a real Slack export directory mounted at /data/slack-export (channels.json + users.json +
#      <channel>/<date>.json), or the anonymized variant (just channel dirs)
#   2. a legacy scraped.json at /data/seed/scraped.json or /data/mattermost/scraped.json
if [ -d /data/slack-export ] && [ -n "$(ls -A /data/slack-export 2>/dev/null)" ]; then
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

# Optional per-task hook (e.g. inject extra planted messages via the gateway after it's up).
[ -x /usr/local/bin/task-seed.sh ] && cp /usr/local/bin/task-seed.sh /tmp/task-seed.sh || true

echo "[boot] starting Slack gateway on :80"
cd /opt
uvicorn slackgw.app:app --host 0.0.0.0 --port 80 --log-level warning --no-server-header &
GW_PID=$!

for _ in $(seq 1 30); do
  curl -s "http://localhost:80/api/auth.test" >/dev/null 2>&1 && break
  sleep 1
done

# Run the optional task hook now that the gateway is reachable.
[ -f /tmp/task-seed.sh ] && bash /tmp/task-seed.sh || true
[ -f /data/seed/seed.sh ] && bash /data/seed/seed.sh || true

echo "[boot] gateway ready"
export GW_PID

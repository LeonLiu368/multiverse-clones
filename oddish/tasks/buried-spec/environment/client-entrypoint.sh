#!/usr/bin/env bash
# Configure mmctl for the agent: log in as admin and wait until the workspace is seeded.
# Leaves an active mmctl auth context named "local" so the agent can run e.g.
#   mmctl post list test-demo:incidents -n 50 --show-ids
#   mmctl post create test-demo:incidents -m "ROOT CAUSE: ..."
# without any further setup. Then sleeps so the container stays up for the task.
set -uo pipefail

URL="${MM_URL:-http://mattermost:8065}"
TEAM="${MM_TEAM:-test-demo}"
USER_ID="${MM_ADMIN_USER:-admin@demo.local}"
PASS="${MM_ADMIN_PASS:-AdminUser123!}"

echo "[client] configuring mmctl against ${URL} (team ${TEAM})..."
authed=0
for i in $(seq 1 120); do
  if mmctl auth login "$URL" --name local --username "$USER_ID" --password "$PASS" >/dev/null 2>&1; then
    if mmctl channel search incidents --team "$TEAM" >/dev/null 2>&1; then
      authed=1
      echo "[client] mmctl authenticated; #incidents is seeded and reachable."
      break
    fi
  fi
  sleep 3
done

if [ "$authed" -ne 1 ]; then
  echo "[client] WARNING: mmctl not fully ready after wait loop; the agent may need to retry 'mmctl auth login'." >&2
fi

exec sleep infinity

#!/usr/bin/env bash
# Healthcheck-as-starter: boot Forgejo (as the non-root `git` user) inside this
# container, seed it once, and write the token to /etc/ghc/token so the gh/ghc
# wrapper picks it up regardless of which user runs it. Idempotent.
set -uo pipefail
DATA=/var/lib/forgejo; BIN=/usr/local/bin/forgejo; CONF=$DATA/conf/app.ini
asgit() { su git -s /bin/bash -c "$1"; }

if ! pgrep -f "forgejo web" >/dev/null 2>&1; then
  mkdir -p $DATA/conf $DATA/data
  cat > $CONF <<INI
APP_NAME = ghc-world
RUN_USER = git
RUN_MODE = prod
WORK_PATH = $DATA
[server]
HTTP_PORT = 3300
ROOT_URL  = http://localhost:3300/
[database]
DB_TYPE = sqlite3
PATH    = $DATA/data/forgejo.db
[security]
INSTALL_LOCK = true
[service]
DISABLE_REGISTRATION = true
[log]
LEVEL = Error
INI
  chown -R git:git $DATA
  nohup su git -s /bin/bash -c "$BIN web --config $CONF --work-path $DATA" >/var/log/forgejo.log 2>&1 &
fi

for i in $(seq 1 90); do
  curl -fsS http://localhost:3300/api/healthz >/dev/null 2>&1 && break || sleep 1
done

if [ ! -f $DATA/.seeded ]; then
  asgit "$BIN admin user create --admin --username ghc-admin --password ghc-pw-0 --email a@local --must-change-password=false --config $CONF --work-path $DATA" >/dev/null 2>&1 || true
  TOKEN=$(asgit "$BIN admin user generate-access-token --username ghc-admin --token-name boot --scopes all --raw --config $CONF --work-path $DATA" 2>/dev/null | tail -1)
  mkdir -p /etc/ghc; echo "$TOKEN" > /etc/ghc/token; chmod 644 /etc/ghc/token
  touch $DATA/.seeded
fi

# optional per-task seeding (creates the repos/issues the task operates on), once
if [ -x /usr/local/bin/task-seed.sh ] && [ ! -f $DATA/.task-seeded ]; then
  GHC_HOST=http://localhost:3300 /usr/local/bin/task-seed.sh && touch $DATA/.task-seeded
fi
curl -fsS http://localhost:3300/api/healthz >/dev/null

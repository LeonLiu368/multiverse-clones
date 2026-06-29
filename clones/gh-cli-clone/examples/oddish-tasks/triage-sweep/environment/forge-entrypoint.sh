#!/usr/bin/env bash
set -uo pipefail
DATA=/var/lib/forgejo; BIN=/usr/local/bin/forgejo; CONF=$DATA/conf/app.ini
asgit(){ su git -s /bin/bash -c "$1"; }
mkdir -p $DATA/conf $DATA/data /shared
cat > $CONF <<INI
APP_NAME = git
RUN_USER = git
RUN_MODE = prod
WORK_PATH = $DATA
[server]
HTTP_PORT = 80
ROOT_URL  = http://10.88.0.2/
[database]
DB_TYPE = sqlite3
PATH = $DATA/data/forgejo.db
[security]
INSTALL_LOCK = true
[service]
DISABLE_REGISTRATION = true
[log]
LEVEL = Error
INI
chown -R git:git $DATA
nohup su git -s /bin/bash -c "$BIN web --config $CONF --work-path $DATA" >/var/log/forgejo.log 2>&1 &
for i in $(seq 1 90); do curl -fsS http://localhost/api/healthz >/dev/null 2>&1 && break || sleep 1; done
if [ ! -f $DATA/.seeded ]; then
  asgit "$BIN admin user create --admin --username acme --password pw --email a@b --must-change-password=false --config $CONF --work-path $DATA" >/dev/null 2>&1 || true
  TOKEN=$(asgit "$BIN admin user generate-access-token --username acme --token-name t --scopes all --raw --config $CONF --work-path $DATA" 2>/dev/null | tail -1)
  echo "$TOKEN" > /shared/token; chmod 644 /shared/token
  # task seed (runs against localhost inside the forge container)
  [ -x /usr/local/bin/task-seed.sh ] && GH_HOST=http://localhost GH_TOKEN="$TOKEN" /usr/local/bin/task-seed.sh || true
  touch $DATA/.seeded
fi
# readiness marker kept forge-internal (NOT on the shared volume) so the agent's
# container never sees an orchestration artifact.
echo "READY" > "$DATA/.ready"
tail -f /var/log/forgejo.log

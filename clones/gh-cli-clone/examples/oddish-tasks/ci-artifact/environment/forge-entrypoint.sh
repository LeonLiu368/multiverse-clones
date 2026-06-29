#!/usr/bin/env bash
# Backend sidecar WITH Actions execution. Boots the git host (port 80, as the
# non-root git user), seeds the task, writes the token to the shared volume, and
# starts a host-mode job runner IN THIS sidecar so workflows actually execute —
# all invisible to the agent's container. Runner setup is fully async so it never
# blocks the healthcheck.
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
[actions]
ENABLED = true
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
  [ -x /usr/local/bin/task-seed.sh ] && GH_HOST=http://localhost GH_TOKEN="$TOKEN" /usr/local/bin/task-seed.sh || true
  touch $DATA/.seeded
fi
# host-mode job runner — async + idempotent; must NEVER block the healthcheck.
if [ ! -f /var/lib/runner/.started ]; then
  mkdir -p /var/lib/runner && touch /var/lib/runner/.started
  # Generated as a standalone script (heredoc, no interpolation) to avoid quoting
  # pitfalls and the parent's `set -u`.
  cat > /usr/local/bin/start-runner.sh <<'RUN'
#!/usr/bin/env bash
cd /var/lib/runner
TOKEN=$(cat /shared/token)
if [ ! -f .runner ]; then
  RTOKEN=$(GH_HOST=http://localhost GH_TOKEN="$TOKEN" /usr/local/bin/gh api admin/runners/registration-token 2>/dev/null \
    | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])' 2>/dev/null)
  # map ubuntu-latest -> host execution so seeded workflows use GitHub's canonical
  # runs-on: ubuntu-latest (no non-GitHub 'host' label tell).
  timeout 60 /usr/local/bin/forgejo-runner register --no-interactive \
    --instance http://localhost --token "$RTOKEN" --name r \
    --labels "ubuntu-latest:host,host:host" >/dev/null 2>&1
fi
exec /usr/local/bin/forgejo-runner daemon
RUN
  chmod +x /usr/local/bin/start-runner.sh
  nohup /usr/local/bin/start-runner.sh >/var/log/runner.log 2>&1 &
fi
# readiness marker kept forge-internal (NOT on the shared volume).
echo "READY" > "$DATA/.ready"
tail -f /var/log/forgejo.log

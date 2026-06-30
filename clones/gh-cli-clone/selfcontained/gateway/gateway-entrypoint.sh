#!/usr/bin/env bash
# Unified gateway entrypoint for the ghc-service image trio.
#
# Three modes, one script — so `:empty` and `:prod-v1` are the SAME image with
# different baked data, and switching a task between them is the image tag alone:
#
#   (default run)  Boot the forge on :80 as the non-root `git` user, publish the
#                  admin token to /shared/token, mark ready, tail logs.
#                    * prod-v1: a corpus DB is BAKED at /var/lib/forgejo. We use
#                      it as-is (mount-free) and publish the BAKED token.
#                    * empty:   no baked corpus. If a per-task fixture is mounted
#                      at $GHC_FIXTURE (default /fixture) we apply it to the live
#                      forge at first boot; otherwise we come up empty.
#
#   --bake         Build-time only (called from Dockerfile.prod-v1). Boots, runs
#                  the corpus seed as admin `acme`, bakes a deterministic token
#                  into /var/lib/forgejo/.baked-token, then exits 0 so the image
#                  layer captures the fully-seeded data dir. NOT used at runtime.
#
# The agent never runs this — it lives only in the gateway container.
set -uo pipefail

DATA=/var/lib/forgejo
BIN=/usr/local/bin/forgejo
CONF=$DATA/conf/app.ini
ROOT_URL="${GHC_ROOT_URL:-http://10.88.0.2/}"
FIXTURE="${GHC_FIXTURE:-/fixture}"
ACTIONS="${GHC_ACTIONS:-false}"
MODE="${1:-run}"

asgit(){ su git -s /bin/bash -c "$1"; }

write_conf() {
  mkdir -p "$DATA/conf" "$DATA/data" /shared
  cat > "$CONF" <<INI
APP_NAME = git
RUN_USER = git
RUN_MODE = prod
WORK_PATH = $DATA
[server]
HTTP_PORT = 80
ROOT_URL  = $ROOT_URL
[database]
DB_TYPE = sqlite3
PATH = $DATA/data/forgejo.db
[security]
INSTALL_LOCK = true
[service]
DISABLE_REGISTRATION = true
[actions]
ENABLED = $ACTIONS
[log]
LEVEL = Error
INI
  chown -R git:git "$DATA"
}

boot_forge() {
  nohup su git -s /bin/bash -c "$BIN web --config $CONF --work-path $DATA" >/var/log/forgejo.log 2>&1 &
  for i in $(seq 1 90); do
    curl -fsS http://localhost/api/healthz >/dev/null 2>&1 && return 0
    sleep 1
  done
  echo "forge did not become healthy" >&2
  cat /var/log/forgejo.log >&2 || true
  return 1
}

ensure_admin_token() {
  # Idempotent: create admin `acme` if absent, then mint an access token. Forgejo
  # stores tokens hashed and mints its own value (you cannot supply one), so the
  # token is always Forgejo-generated; we bake whatever it returns. Returns the
  # token on stdout.
  asgit "$BIN admin user create --admin --username acme --password pw --email a@b --must-change-password=false --config $CONF --work-path $DATA" >/dev/null 2>&1 || true
  asgit "$BIN admin user generate-access-token --username acme --token-name t --scopes all --raw --config $CONF --work-path $DATA" 2>/dev/null | tail -1
}

# ---- build-time bake (prod-v1) -------------------------------------------------
if [ "$MODE" = "--bake" ]; then
  write_conf
  boot_forge || exit 1
  TOKEN=$(ensure_admin_token)
  if [ -z "$TOKEN" ]; then echo "failed to mint admin token at bake time" >&2; exit 1; fi
  # Run the corpus seed against the local forge.
  if [ -x /usr/local/bin/corpus-seed.sh ]; then
    GH_HOST=http://localhost GH_TOKEN="$TOKEN" /usr/local/bin/corpus-seed.sh || { echo "corpus seed failed" >&2; exit 1; }
  fi
  # Bake the token so the runtime entrypoint can publish it without minting a new
  # one (keeps :prod-v1 deterministic and mount-free).
  printf '%s' "$TOKEN" > "$DATA/.baked-token"
  touch "$DATA/.seeded"
  # Graceful shutdown so SQLite flushes WAL into the baked layer.
  pkill -TERM -f "$BIN web" 2>/dev/null || true
  for i in $(seq 1 20); do pgrep -f "$BIN web" >/dev/null 2>&1 || break; sleep 1; done
  chown -R git:git "$DATA"
  echo "baked corpus + token into $DATA"
  exit 0
fi

# ---- runtime -------------------------------------------------------------------
write_conf

if [ -f "$DATA/.baked-token" ]; then
  # prod-v1: baked corpus DB is already on disk. Boot it as-is, publish the baked
  # token. No seeding, no mount.
  boot_forge || exit 1
  cp "$DATA/.baked-token" /shared/token
  chmod 644 /shared/token
else
  # empty (+ optional per-task mount). Boot, mint token, optionally apply fixture.
  boot_forge || exit 1
  if [ ! -f "$DATA/.seeded" ]; then
    TOKEN=$(ensure_admin_token)
    echo "$TOKEN" > /shared/token; chmod 644 /shared/token
    # Per-task fixture (mounted into the gateway, applied to a RUNTIME copy).
    # Supported fixture shapes (first match wins):
    #   $FIXTURE/seed.sh           — a shell seed (run with GH_HOST/GH_TOKEN set)
    #   $FIXTURE/forgejo-data.tgz  — a tarball of a pre-seeded $DATA (rare)
    if [ -x "$FIXTURE/seed.sh" ] || [ -f "$FIXTURE/seed.sh" ]; then
      GH_HOST=http://localhost GH_TOKEN="$TOKEN" bash "$FIXTURE/seed.sh" || echo "fixture seed.sh failed" >&2
    fi
    touch "$DATA/.seeded"
  else
    # Already seeded on a prior boot (persistent volume); just republish token.
    TOKEN=$(ensure_admin_token)
    echo "$TOKEN" > /shared/token; chmod 644 /shared/token
  fi
fi

# Optional Actions runner (host-mode), fully async; never blocks readiness.
if [ "$ACTIONS" = "true" ] && [ ! -f /var/lib/runner/.started ] && [ -x /usr/local/bin/forgejo-runner ]; then
  mkdir -p /var/lib/runner && touch /var/lib/runner/.started
  cat > /usr/local/bin/start-runner.sh <<'RUN'
#!/usr/bin/env bash
cd /var/lib/runner
TOKEN=$(cat /shared/token)
if [ ! -f .runner ]; then
  RTOKEN=$(GH_HOST=http://localhost GH_TOKEN="$TOKEN" /usr/local/bin/gh api admin/runners/registration-token 2>/dev/null \
    | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])' 2>/dev/null)
  timeout 60 /usr/local/bin/forgejo-runner register --no-interactive \
    --instance http://localhost --token "$RTOKEN" --name r \
    --labels "ubuntu-latest:host,host:host" >/dev/null 2>&1
fi
exec /usr/local/bin/forgejo-runner daemon
RUN
  chmod +x /usr/local/bin/start-runner.sh
  nohup /usr/local/bin/start-runner.sh >/var/log/runner.log 2>&1 &
fi

# readiness marker kept forge-internal (NOT on the shared volume) so the agent's
# container never sees an orchestration artifact.
echo "READY" > "$DATA/.ready"
tail -f /var/log/forgejo.log

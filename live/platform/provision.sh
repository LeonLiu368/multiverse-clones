#!/usr/bin/env bash
# Provision the Dokku deploy plane for a live task. Run at task SETUP (from the
# main/setup context, host-side), after `docker compose up -d` has started the
# `dokku` service. Idempotent where possible.
#
# What it does (proven spike mode, see ../README.md):
#   1. wait for `dokku version` to answer
#   2. apps:create <app>            (idempotent)
#   3. ssh-keys:add for the agent key (idempotent)
#   4. network:set <app> attach-post-create <net>  (so app joins task network)
#   5. events:on                    (verifier audit trail)
#   6. config:set <app> <FAULTY env> (arm the P4 fault; e.g. DB_POOL_SIZE=1)
#   7. provision a Postgres for the app + set DATABASE_URL   (if --pg)
#   8. git push deploy the SUT (Dockerfile build) from --sut-dir
#   9. wait until <app>.web.1 answers /health
#
# Usage:
#   provision.sh \
#     --dokku-container <name>       (docker container name of the dokku service; default: dokku)
#     --app conduit \
#     --net <compose-network-name>   (e.g. mytask_default; REQUIRED)
#     --key /path/to/agent_key.pub   (agent public key to authorize; REQUIRED)
#     --sut-dir ../sut-conduit       (git dir to push; REQUIRED for deploy)
#     --config "DB_POOL_SIZE=1 WRITE_WORK_SECONDS=0.05"   (faulty runtime config)
#     --port 8000                    (port the app listens on; default 8000)
#     [--pg]                         (provision a dokku postgres + link, else expects DATABASE_URL in --config)
#     [--ssh-port 3022]              (host port mapped to dokku:22 for git push; default 3022)
#     [--no-deploy]                  (setup only, skip git push)
set -euo pipefail

DOKKU_CONTAINER="dokku"
APP="conduit"
NET=""
KEY=""
SUT_DIR=""
CONFIG=""
PORT="8000"
PROVISION_PG=0
SSH_PORT="3022"
DO_DEPLOY=1

while [ $# -gt 0 ]; do
  case "$1" in
    --dokku-container) DOKKU_CONTAINER="$2"; shift 2;;
    --app) APP="$2"; shift 2;;
    --net) NET="$2"; shift 2;;
    --key) KEY="$2"; shift 2;;
    --sut-dir) SUT_DIR="$2"; shift 2;;
    --config) CONFIG="$2"; shift 2;;
    --port) PORT="$2"; shift 2;;
    --pg) PROVISION_PG=1; shift;;
    --ssh-port) SSH_PORT="$2"; shift 2;;
    --no-deploy) DO_DEPLOY=0; shift;;
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac
done

[ -n "$NET" ] || { echo "ERROR: --net (compose network) required" >&2; exit 2; }
[ -n "$KEY" ] || { echo "ERROR: --key (agent pub key) required" >&2; exit 2; }

# Resolve KEY to an absolute path — git push runs ssh from $SUT_DIR, so a
# relative -i identity path would not resolve.
case "$KEY" in
  /*) : ;;
  *) KEY="$(cd "$(dirname "$KEY")" && pwd)/$(basename "$KEY")" ;;
esac

dk() { docker exec -i "$DOKKU_CONTAINER" dokku "$@"; }
log() { echo "[provision] $*"; }

# 1. wait for dokku
log "waiting for dokku to be ready..."
for i in $(seq 1 60); do
  if docker exec "$DOKKU_CONTAINER" dokku version >/dev/null 2>&1; then
    log "dokku ready ($(docker exec "$DOKKU_CONTAINER" dokku version 2>/dev/null | head -1))"; break
  fi
  sleep 2
  [ "$i" = 60 ] && { echo "ERROR: dokku never came up" >&2; exit 1; }
done

# 2. apps:create (idempotent)
if dk apps:exists "$APP" >/dev/null 2>&1; then
  log "app '$APP' already exists"
else
  log "creating app '$APP'"; dk apps:create "$APP"
fi

# 3. authorize the agent key (idempotent: remove-then-add on the same name)
log "authorizing agent key from $KEY"
dk ssh-keys:remove agent >/dev/null 2>&1 || true
docker exec -i "$DOKKU_CONTAINER" dokku ssh-keys:add agent < "$KEY"

# 4. attach-post-create so app containers join the task network
log "network:set $APP attach-post-create $NET"
dk network:set "$APP" attach-post-create "$NET"

# 5. events on (audit trail for the verifier)
log "enabling dokku events (audit trail)"
dk events:on || true

# 7. optional: provision a dokku postgres and link it (sets DATABASE_URL)
if [ "$PROVISION_PG" = 1 ]; then
  if docker exec "$DOKKU_CONTAINER" dokku postgres:exists "${APP}-db" >/dev/null 2>&1; then
    log "postgres '${APP}-db' already exists"
  else
    log "installing postgres plugin + creating ${APP}-db (first run pulls the postgres image)"
    docker exec "$DOKKU_CONTAINER" bash -lc \
      'dokku plugin:list | grep -q postgres || dokku plugin:install https://github.com/dokku/dokku-postgres.git'
    dk postgres:create "${APP}-db"
  fi
  dk postgres:link "${APP}-db" "$APP" || true   # link sets DATABASE_URL on the app
fi

# 6. arm the fault + any extra runtime config (single redeploy). config:set with
#    --no-restart here since we deploy right after; the deploy brings it up armed.
if [ -n "$CONFIG" ]; then
  log "config:set (arming fault): $CONFIG"
  # shellcheck disable=SC2086
  dk config:set --no-restart "$APP" $CONFIG
fi

# 8. deploy the SUT via git push (Dockerfile build)
if [ "$DO_DEPLOY" = 1 ]; then
  [ -n "$SUT_DIR" ] || { echo "ERROR: --sut-dir required to deploy (or pass --no-deploy)" >&2; exit 2; }
  log "deploying $APP from $SUT_DIR via git push (Dockerfile build)"
  # Build a throwaway git repo in a temp dir (a copy of the SUT source) rather
  # than polluting $SUT_DIR with a nested .git — dokku only needs a commit to
  # push, and this keeps the source tree clean for the enclosing repo.
  TMP_REPO="$(mktemp -d)"
  trap 'rm -rf "$TMP_REPO"' EXIT
  # copy source (exclude any VCS/build cruft)
  tar -C "$SUT_DIR" --exclude='.git' --exclude='__pycache__' --exclude='_otel_out' -cf - . \
    | tar -C "$TMP_REPO" -xf -
  ( cd "$TMP_REPO" \
      && git init -q \
      && git add -A \
      && git -c user.email=setup@live -c user.name=setup commit -qm "sut snapshot" )
  # Push over ssh to dokku using the PRIVATE key that pairs with the authorized
  # --key. Host reaches dokku at localhost:<ssh-port>; from a sibling container
  # use dokku@dokku (port 22). We use the host mapping here.
  # Derive the private key path from the public key path (strip a trailing .pub).
  PRIV_KEY="${KEY%.pub}"
  [ -f "$PRIV_KEY" ] || { echo "ERROR: private key $PRIV_KEY not found (need it to git push)" >&2; exit 1; }
  GIT_SSH_COMMAND="ssh -i ${PRIV_KEY} -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -p ${SSH_PORT}" \
    git -C "$TMP_REPO" push -f "dokku@localhost:${APP}" HEAD:refs/heads/main
fi

# 9. wait until the app answers health from a sibling on the task network.
#    We probe by running a throwaway curl container ON the task network.
log "waiting for ${APP}.web.1:${PORT}/health ..."
for i in $(seq 1 60); do
  if docker run --rm --network "$NET" curlimages/curl:8.11.1 \
       -sf -m3 "http://${APP}.web.1:${PORT}/health" >/dev/null 2>&1; then
    log "HEALTHY: ${APP}.web.1:${PORT}/health answered"
    docker run --rm --network "$NET" curlimages/curl:8.11.1 \
       -s "http://${APP}.web.1:${PORT}/health" || true
    echo
    break
  fi
  sleep 2
  [ "$i" = 60 ] && { echo "ERROR: ${APP} never became healthy" >&2; dk logs "$APP" --num 40 || true; exit 1; }
done

log "provision complete. agent surface: ssh dokku@dokku ... ; git push dokku@dokku:${APP}"

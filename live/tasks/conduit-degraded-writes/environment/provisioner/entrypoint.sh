#!/usr/bin/env bash
# One-shot provisioner for the conduit-degraded-writes task.
#
# Runs after postgres/logfire/otel-collector/dokku are healthy. It:
#   1. generates the agent SSH keypair into the shared `keys` volume
#      (pubkey -> dokku authorizes it; privkey -> the agent/main container uses it)
#   2. assembles the SUT deploy repo (vendored conduit app/ + otel-wrap overlay)
#      into the shared `sut` volume that the dokku container sees at /mnt/sut
#   3. runs provision-gitsync.sh: dokku events:on, ssh-keys:add, apps:create,
#      config:set (the FAULT: WEB_CONCURRENCY=1) + OTEL + DATABASE_URL + SECRET_KEY,
#      network:set attach-post-create <task net>, git:sync --build deploy, wait healthy
#   4. seeds a few users/articles so read flows have data
#   5. drops a readiness marker into the shared `state` volume, then exits 0
set -euo pipefail

DOKKU_CONTAINER="${DOKKU_CONTAINER:-conduit-degraded-writes-dokku-1}"
APP="${APP:-conduit}"
PORT="${PORT:-8000}"
KEYS_DIR=/mnt/keys          # shared volume (also mounted into dokku + main)
SUT_DIR=/mnt/sut            # shared volume (also mounted into dokku at /mnt/sut)
STATE_DIR=/mnt/state        # shared volume (main waits on the marker here)
SRC=/opt/sut-src            # baked-in SUT source (vendored app/ + otel-wrap/)

log() { echo "[provisioner $(date +%H:%M:%S)] $*"; }

# 1. agent keypair (idempotent)
mkdir -p "$KEYS_DIR"
if [ ! -f "$KEYS_DIR/agent_key" ]; then
  ssh-keygen -t ed25519 -N "" -C agent -f "$KEYS_DIR/agent_key" >/dev/null
  chmod 644 "$KEYS_DIR/agent_key.pub"; chmod 600 "$KEYS_DIR/agent_key"
  log "generated agent keypair in $KEYS_DIR"
fi

# 2. assemble SUT deploy repo (vendored source + otel overlay) into shared volume
log "assembling SUT deploy repo into $SUT_DIR"
rm -rf "$SUT_DIR"/* 2>/dev/null || true
cp -R "$SRC/app/." "$SUT_DIR/"
cp "$SRC/otel-wrap/Dockerfile" "$SRC/otel-wrap/requirements.txt" "$SUT_DIR/"

# 3. provision + faulty deploy. SECRET_KEY random; OTEL points at the collector.
SECRET="$(openssl rand -hex 16 2>/dev/null || echo task-secret-$$)"
FAULTY_CONFIG="DATABASE_URL=postgresql://conduit:conduit@postgres:5432/conduit \
SECRET_KEY=$SECRET \
WEB_CONCURRENCY=1 \
MAX_CONNECTIONS_COUNT=10 MIN_CONNECTIONS_COUNT=5 \
OTEL_SERVICE_NAME=conduit \
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318 \
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf \
OTEL_TRACES_EXPORTER=otlp OTEL_METRICS_EXPORTER=none OTEL_LOGS_EXPORTER=none"

# Pin the dokku port mapping to http:80:8000 BEFORE deploy so dokku deterministically
# injects PORT=8000 into the app (the app honors $PORT; the whole task targets
# conduit.web.1:8000). The nginx vhost proxy itself is unused (siblings hit the
# container directly by name), but keeping the proxy ENABLED with a fixed mapping
# is what makes dokku set PORT=8000 stably across every redeploy — including the
# agent's config:set remediation. (Disabling the proxy makes dokku fall back to
# PORT=5000 and hangs redeploys on the nginx-reload step in sibling mode.)
log "creating app + pinning port map http:80:8000 + disabling deploy checks"
docker exec "$DOKKU_CONTAINER" dokku apps:create "$APP" >/dev/null 2>&1 || true
docker exec "$DOKKU_CONTAINER" dokku ports:set "$APP" http:80:8000 >/dev/null 2>&1 || true
# Disable dokku's zero-downtime deploy checks. Its port-listening check uses
# `nsenter` into the app container, which fails in socket-sibling mode and makes
# every redeploy (including the agent's config:set fix) slow/flaky. The app's real
# health is gated by the soak verifier and this provisioner directly.
docker exec "$DOKKU_CONTAINER" dokku checks:disable "$APP" >/dev/null 2>&1 || true

log "running provision-gitsync (faulty WEB_CONCURRENCY=1)"
# Tolerate a non-zero exit from the deploy: dokku's post-deploy nginx-proxy
# rebuild can fail in socket-sibling mode (a stale nginx.conf conflict), which
# makes `git:sync` return non-zero even though the app container deployed and is
# serving. The nginx vhost is unused (siblings hit conduit.web.1:8000 directly),
# so we gate on ACTUAL health below, not on provision-gitsync's exit code.
set +e
/opt/platform/provision-gitsync.sh \
  --dokku-container "$DOKKU_CONTAINER" \
  --app "$APP" \
  --pubkey "$KEYS_DIR/agent_key.pub" \
  --sut "$SUT_DIR" \
  --config "$FAULTY_CONFIG" \
  --port "$PORT" \
  --health-path /api/tags
PG_RC=$?
set -e
[ "$PG_RC" -eq 0 ] && log "provision-gitsync OK" || log "provision-gitsync rc=$PG_RC (tolerated; gating on health)"

# Gate on the app actually answering health from a sibling (the real signal).
BASE="http://$APP.web.1:$PORT"
log "confirming $APP.web.1:$PORT is healthy"
i=0
until docker exec "$DOKKU_CONTAINER" curl -fsS -m3 "$BASE/api/tags" >/dev/null 2>&1; do
  i=$((i+1)); [ "$i" -lt 90 ] || { echo "[provisioner] FATAL: $APP never healthy" >&2; exit 1; }
  sleep 2
done
log "$APP healthy on 8000"

# 4. seed (idempotent). The app is reachable by container name on the task net.
log "seeding fixtures at $BASE"
python3 /opt/sut-src/otel-wrap/seed.py --base "$BASE" || log "seed warning (continuing)"

# Extra: a fixed user the soak verifier's login_churn flow logs in as (bcrypt CPU).
log "registering soak login user"
curl -sS -m 10 -X POST "$BASE/api/users" -H 'Content-Type: application/json' \
  -d '{"user":{"username":"soakfixed","email":"soakfixed@ex.com","password":"soaksoak123"}}' \
  >/dev/null 2>&1 || true

# 5. readiness marker for main (in case Harbor can't do service_completed_successfully)
mkdir -p "$STATE_DIR"
echo "ready $(date -u +%FT%TZ)" > "$STATE_DIR/provisioned"
log "PROVISION COMPLETE — marker written to $STATE_DIR/provisioned"

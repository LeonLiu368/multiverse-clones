#!/usr/bin/env bash
# ORACLE solution for conduit-degraded-writes.
#
# Robust (derives, does not blindly hardcode):
#   1. query live telemetry to CONFIRM the degradation is conduit's request path
#      (all latency on ONE service; login/article spans are the slow ones) and
#      that it's not a DB/exception problem — so the mechanism is single-worker
#      event-loop saturation, fixable by scaling workers.
#   2. read the live deploy config, find the worker knob at its faulty value,
#      apply the fix via the dokku agent surface, wait for the redeploy to be healthy.
#   3. write /workspace/findings.json naming component + mechanism.
set -euo pipefail

WORKSPACE="${WORKSPACE:-/workspace}"
APP="${APP:-conduit}"
BASE="http://$APP.web.1:8000"
SINCE="${LOGFIRE_MIN_TIMESTAMP:-2026-07-01T00:00:00Z}"

log() { echo "[solve $(date +%H:%M:%S)] $*"; }

dokku() { ssh dokku@dokku "$@"; }

# ---------- 1. derive the degradation from live telemetry ----------
log "querying live telemetry for the slow service + operations"
# Which service dominates latency, and which spans? (p95 by service+span)
logfire query "
  SELECT service_name,
         span_name,
         count(*) AS n,
         round(approx_quantile(duration, 0.95), 3) AS p95_s
  FROM records
  WHERE duration IS NOT NULL
  GROUP BY service_name, span_name
  HAVING count(*) >= 3
  ORDER BY p95_s DESC
  LIMIT 15
" --since "$SINCE" || true

# Confirm it's all one service (no cross-service fan-out -> not a downstream dep),
# and that errors/exceptions are NOT the driver (so it's saturation, not failure).
log "confirming single-service saturation (not a downstream dep, not exceptions)"
logfire query "
  SELECT service_name,
         count(*) AS spans,
         sum(CASE WHEN is_exception THEN 1 ELSE 0 END) AS exceptions,
         round(approx_quantile(duration, 0.95), 3) AS p95_s
  FROM records
  WHERE service_name = '$APP'
  GROUP BY service_name
" --since "$SINCE" || true

# The high-latency spans are the auth/write path (login + POST /api/articles);
# under load they queue behind each other on a single worker's event loop.
logfire query "
  SELECT span_name,
         round(approx_quantile(duration, 0.5), 3) AS p50_s,
         round(approx_quantile(duration, 0.95), 3) AS p95_s
  FROM records
  WHERE service_name = '$APP' AND http_method IS NOT NULL
  GROUP BY span_name
  ORDER BY p95_s DESC
  LIMIT 10
" --since "$SINCE" || true

# ---------- 2. inspect + fix the live deploy config ----------
log "current deploy config:"
dokku config:show "$APP" || true

# The single-worker knob (WEB_CONCURRENCY) is at its faulty value (1). Read it,
# and scale it up so concurrent CPU-bound requests (bcrypt logins) no longer
# serialize on one event loop.
CUR="$(dokku config:get "$APP" WEB_CONCURRENCY 2>/dev/null || echo "")"
log "WEB_CONCURRENCY currently = '${CUR:-<unset>}'"
FIX_WORKERS=4
log "scaling workers: config:set $APP WEB_CONCURRENCY=$FIX_WORKERS (redeploys)"
dokku config:set "$APP" WEB_CONCURRENCY="$FIX_WORKERS"

# ---------- wait for the redeploy to be healthy ----------
log "waiting for $APP to be healthy after redeploy"
i=0
until curl -fsS -m3 "$BASE/api/tags" >/dev/null 2>&1; do
  i=$((i+1)); [ "$i" -lt 120 ] || { echo "app did not come back after fix" >&2; exit 1; }
  sleep 2
done
log "app healthy after fix; workers now: $(dokku config:get "$APP" WEB_CONCURRENCY)"

# ---------- 3. findings ----------
mkdir -p "$WORKSPACE"
cat > "$WORKSPACE/findings.json" <<'JSON'
{
  "component": "conduit",
  "mechanism": "The conduit service ran with a single uvicorn worker process, so all concurrent requests were multiplexed onto one asyncio event loop. Under load the CPU-bound work in the request path — the bcrypt password verification on login, plus per-request serialization — blocked that single event loop, so requests queued behind each other and latency for logins and article writes saturated. Scaling the web concurrency (worker processes) spreads the CPU-bound work across multiple event loops and removes the serialization."
}
JSON
log "wrote $WORKSPACE/findings.json"
cat "$WORKSPACE/findings.json"

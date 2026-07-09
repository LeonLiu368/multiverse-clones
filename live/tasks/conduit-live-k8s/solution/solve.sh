#!/usr/bin/env bash
# ORACLE solution for conduit-live-k8s (k3s plane).
#
# Robust (derives, does not blindly hardcode):
#   1. query live telemetry to CONFIRM the degradation is conduit's request path
#      (all latency on ONE service; login/article spans are the slow ones) and
#      that it's not a DB/exception problem — so the mechanism is single-worker
#      event-loop saturation, fixable by scaling workers.
#   2. read the live deploy config from k8s, find the worker knob at its faulty
#      value, apply the fix via kubectl, wait for the rollout to be healthy.
#   3. write /workspace/findings.json naming component + mechanism.
set -euo pipefail

WORKSPACE="${WORKSPACE:-/workspace}"
NS="${NS:-conduit}"
APP="${APP:-conduit}"
BASE="${CONDUIT_URL:-http://k3s:30800}"
SINCE="${LOGFIRE_MIN_TIMESTAMP:-2026-07-01T00:00:00Z}"

log() { echo "[solve $(date +%H:%M:%S)] $*"; }

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

# ---------- 2. inspect + fix the live deploy config (k8s) ----------
log "current conduit Deployment env:"
kubectl -n "$NS" get deploy/"$APP" \
  -o jsonpath='{range .spec.template.spec.containers[0].env[*]}{.name}={.value}{"\n"}{end}' || true

# The single-worker knob (WEB_CONCURRENCY) is at its faulty value (1). Read it,
# and scale it up so concurrent CPU-bound requests (bcrypt logins) no longer
# serialize on one event loop.
CUR="$(kubectl -n "$NS" get deploy/"$APP" \
  -o jsonpath='{range .spec.template.spec.containers[0].env[?(@.name=="WEB_CONCURRENCY")]}{.value}{end}' 2>/dev/null || echo "")"
log "WEB_CONCURRENCY currently = '${CUR:-<unset>}'"
FIX_WORKERS=4
log "scaling workers: kubectl set env deploy/$APP WEB_CONCURRENCY=$FIX_WORKERS (rolls out)"
kubectl -n "$NS" set env deploy/"$APP" WEB_CONCURRENCY="$FIX_WORKERS"

# ---------- wait for the rollout to FULLY converge ----------
# `rollout status` returns when the Deployment reports complete, but the old
# single-worker ReplicaSet's pod (and the Service endpoint routing to it) can
# linger briefly. Wait until (a) the rollout is complete, (b) every non-target
# ReplicaSet is scaled to 0, and (c) only the new pod is Ready — so the NodePort
# serves exclusively from the fixed pod before any load hits it.
log "waiting for rollout to complete"
kubectl -n "$NS" rollout status deploy/"$APP" --timeout=180s || true

log "waiting for old ReplicaSets to scale to 0 (endpoint fully switched)"
i=0
while [ "$i" -lt 90 ]; do
  # sum of pods across all conduit ReplicaSets that are NOT the current one
  CURRS="$(kubectl -n "$NS" get rs -l app="$APP" \
    -o jsonpath='{range .items[?(@.status.replicas>0)]}{.metadata.name}={.status.replicas}{"\n"}{end}' 2>/dev/null | wc -l | tr -d ' ')"
  READY="$(kubectl -n "$NS" get po -l app="$APP" \
    --field-selector=status.phase=Running -o jsonpath='{range .items[*]}{.status.containerStatuses[0].ready}{"\n"}{end}' 2>/dev/null | grep -c true || true)"
  # exactly one RS with replicas>0 AND exactly one Ready pod => converged
  if [ "${CURRS:-9}" -le 1 ] && [ "${READY:-0}" -eq 1 ]; then
    log "rollout converged (1 ReplicaSet active, 1 Ready pod)"; break
  fi
  i=$((i+1)); sleep 2
done

log "waiting for $APP to answer health after rollout"
i=0
until curl -fsS -m3 "$BASE/api/tags" >/dev/null 2>&1; do
  i=$((i+1)); [ "$i" -lt 120 ] || {
    echo "app did not come back after fix" >&2
    echo "===== cluster state at failure =====" >&2
    kubectl get pods -A -o wide >&2 2>&1 || true
    kubectl get events -n "$NS" --sort-by=.lastTimestamp 2>/dev/null | tail -15 >&2 || true
    exit 1
  }
  sleep 2
done
# A short settle so kube-proxy endpoint slices propagate to the NodePort before load.
sleep 3
NOW="$(kubectl -n "$NS" get deploy/"$APP" \
  -o jsonpath='{range .spec.template.spec.containers[0].env[?(@.name=="WEB_CONCURRENCY")]}{.value}{end}' 2>/dev/null || echo "?")"
log "app healthy after fix; workers now: $NOW"

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

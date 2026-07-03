#!/usr/bin/env bash
# smoke.sh — end-to-end proof of the live-deployment primitives, self-contained.
#
#   1. compose up: dokku (socket-sibling) + postgres:16 + python probe sibling
#   2. provision + deploy the VENDORED Conduit SUT with the FAULTY env
#      (WEB_CONCURRENCY=1) via provision-gitsync.sh (git:sync --build, no SSH)
#   3. prove, from the probe:
#      (a) app healthy on the DIRECT container-name path (<app>.web.1:8000)
#      (b) login + create-article API round-trip works
#      (c) concurrent load (12 writers x 20 iterations, mixed write+read with
#          session churn) degrades under the faulty config (p50/p95/error rate)
#      (d) `ssh dokku@dokku config:set` fix (the AGENT surface) + redeploy,
#          same load is now healthy
#   4. write timings + degraded-vs-fixed numbers to SMOKE-RESULTS.md
#   5. clean up containers/network/dokku host state (SMOKE_KEEP=1 to skip)
#
# Env overrides: SMOKE_PROJECT (compose project, default livesmoke),
# SMOKE_KEY_DIR (pre-generated keypair dir containing agent_key/agent_key.pub;
# generated if absent), SMOKE_KEEP=1 (leave the stack running).
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
LIVE=$(cd "$HERE/.." && pwd)
PROJ=${SMOKE_PROJECT:-livesmoke}
APP="$PROJ-conduit"                    # namespaced: container names are global on a shared dockerd
PORT=8000
BASE="http://$APP.web.1:$PORT"
WORK=$(mktemp -d /tmp/dokku-smoke.XXXXXX)
RESULTS="$HERE/SMOKE-RESULTS.md"
SSH_OPTS="-i /root/.ssh/agent_key -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR"

say() { echo "[smoke $(date +%H:%M:%S)] $*"; }

# ---------- keys (pre-generated keypair path supported) ----------
KEY_DIR=${SMOKE_KEY_DIR:-$WORK/keys}
mkdir -p "$KEY_DIR"
if [ ! -f "$KEY_DIR/agent_key" ]; then
  ssh-keygen -t ed25519 -N "" -C agent -f "$KEY_DIR/agent_key" >/dev/null
  say "generated agent keypair in $KEY_DIR"
else
  say "using pre-generated keypair in $KEY_DIR"
fi

# ---------- assemble the SUT deploy repo (vendored source + otel overlay) ----------
cp -R "$LIVE/sut-conduit/app" "$WORK/sut-repo"
cp "$LIVE/sut-conduit/otel-wrap/Dockerfile" \
   "$LIVE/sut-conduit/otel-wrap/requirements.txt" "$WORK/sut-repo/"
say "SUT repo assembled at $WORK/sut-repo"

export SUT_REPO_DIR="$WORK/sut-repo"
export AGENT_PUBKEY="$KEY_DIR/agent_key.pub"
export AGENT_KEY="$KEY_DIR/agent_key"
export SCRIPTS_DIR="$LIVE/sut-conduit/otel-wrap"

compose() { docker compose -p "$PROJ" -f "$HERE/smoke-compose.yaml" "$@"; }
pexec()   { docker exec "$PROJ-probe-1" "$@"; }

cleanup() {
  [ "${SMOKE_KEEP:-0}" = "1" ] && { say "SMOKE_KEEP=1 — leaving stack up"; return; }
  say "cleaning up..."
  docker ps -aq --filter "name=$APP" | xargs -r docker rm -f >/dev/null 2>&1 || true
  compose down -v --remove-orphans >/dev/null 2>&1 || true
  docker rmi "dokku/$APP:latest" >/dev/null 2>&1 || true
  docker run --rm -v /var/lib:/vl alpine:3.20 rm -rf "/vl/dokku-$PROJ" >/dev/null 2>&1 || true
  rm -rf "$WORK"
  say "cleanup done (results kept in $RESULTS)"
}
trap cleanup EXIT

T_START=$SECONDS

# ---------- 1. compose up ----------
compose up -d
T_UP=$((SECONDS-T_START))
say "compose up done (${T_UP}s)"

# probe tooling: ssh client (the agent surface) — python is already the image
t=$SECONDS
pexec sh -c "apt-get update -qq >/dev/null && apt-get install -y -qq openssh-client >/dev/null 2>&1"
pexec sh -c "mkdir -p /root/.ssh && cp /keys/agent_key /root/.ssh/agent_key && chmod 600 /root/.ssh/agent_key"
T_PROBE_PREP=$((SECONDS-t))
say "probe prepared: openssh-client + key (${T_PROBE_PREP}s)"

# ---------- 2. provision + deploy with FAULTY env ----------
SECRET=$(openssl rand -hex 16 2>/dev/null || echo smoke-secret-$$)
FAULTY_CONFIG="DATABASE_URL=postgresql://conduit:conduit@postgres:5432/conduit \
SECRET_KEY=$SECRET \
WEB_CONCURRENCY=1 \
MAX_CONNECTIONS_COUNT=10 MIN_CONNECTIONS_COUNT=5 \
OTEL_SDK_DISABLED=true \
OTEL_TRACES_EXPORTER=none OTEL_METRICS_EXPORTER=none OTEL_LOGS_EXPORTER=none \
OTEL_SERVICE_NAME=conduit"
t=$SECONDS
"$HERE/provision-gitsync.sh" \
  --dokku-container "$PROJ-dokku-1" \
  --app "$APP" \
  --config "$FAULTY_CONFIG" \
  --port "$PORT" \
  --health-path /api/tags
T_PROVISION=$((SECONDS-t))
say "provision + faulty deploy done (${T_PROVISION}s)"

# ---------- 3a. healthy on direct container name, from the probe ----------
t=$SECONDS
pexec python3 -c "
import urllib.request,sys
r=urllib.request.urlopen('$BASE/api/tags',timeout=5)
assert r.status==200, r.status
print('probe -> $BASE/api/tags OK (HTTP',r.status,')')"
T_DIRECT=$((SECONDS-t))

# seed fixture
pexec python3 /scripts/seed.py --base "$BASE"

# ---------- 3b. login / create-article round trip ----------
pexec python3 - <<PYEOF
import json, urllib.request
base = "$BASE"
def api(method, path, body=None, token=None):
    req = urllib.request.Request(base+path,
        data=json.dumps(body).encode() if body else None, method=method)
    req.add_header("Content-Type", "application/json")
    if token: req.add_header("Authorization", "Token "+token)
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.status, json.loads(r.read())
s, u = api("POST", "/api/users/login",
           {"user": {"email": "alice@conduit.dev", "password": "password123"}})
assert s == 200, s
tok = u["user"]["token"]
s, a = api("POST", "/api/articles",
           {"article": {"title": "smoke round trip", "description": "rt",
                        "body": "round trip body", "tagList": ["smoke"]}}, tok)
assert s in (200, 201), s
slug = a["article"]["slug"]
s, got = api("GET", "/api/articles/"+slug)
assert s == 200 and got["article"]["title"] == "smoke round trip"
print("round trip OK: login -> create -> read back (slug=%s)" % slug)
PYEOF
say "login/create-article round trip OK"

# ---------- 3c. concurrent load against the FAULTY config ----------
say "load (FAULTY, WEB_CONCURRENCY=1): 12 writers x 20 iters, mixed + login churn"
t=$SECONDS
FAULTY_JSON=$(pexec python3 /scripts/load_probe.py --base "$BASE" \
  --writers 12 --requests 20 --mode mixed --login-every 5 --label faulty)
T_LOAD_FAULTY=$((SECONDS-t))
echo "$FAULTY_JSON"

# ---------- 3d. the fix, via the AGENT surface (ssh) ----------
say "applying fix via agent surface: ssh dokku@dokku config:set $APP WEB_CONCURRENCY=4"
t=$SECONDS
# The restart triggered by config:set can exit nonzero on non-fatal check
# warnings; do not die on rc — the REAL gates are config:get + health + load.
set +e
FIX_OUT=$(pexec ssh $SSH_OPTS "dokku@dokku" config:set "$APP" WEB_CONCURRENCY=4 2>&1)
FIX_RC=$?
set -e
echo "$FIX_OUT" | tail -8
say "config:set returned rc=$FIX_RC"
# wait for the redeployed app to answer again
pexec python3 -c "
import time,urllib.request,sys
deadline=time.time()+240
while True:
    try:
        r=urllib.request.urlopen('$BASE/api/tags',timeout=3)
        if r.status==200: break
    except Exception: pass
    if time.time()>deadline: sys.exit('app did not come back after fix')
    time.sleep(2)
print('app back after fix')"
T_FIX=$((SECONDS-t))
say "fix + redeploy done (${T_FIX}s)"

# verify the fix took, via the agent surface + worker count in app logs
FIXED_VAL=$(pexec ssh $SSH_OPTS "dokku@dokku" config:get "$APP" WEB_CONCURRENCY | tr -d '\r\n')
[ "$FIXED_VAL" = "4" ] || { echo "ERROR: fix did not apply (WEB_CONCURRENCY=$FIXED_VAL)" >&2; exit 1; }
WORKERS_STARTED=$(docker logs "$APP.web.1" 2>&1 | grep -oE 'Started server process \[[0-9]+\]' | sort -u | wc -l | tr -d ' ')
say "config:get WEB_CONCURRENCY=$FIXED_VAL; uvicorn workers started: $WORKERS_STARTED"

# ---------- same load, FIXED config ----------
say "load (FIXED, WEB_CONCURRENCY=4): same workload"
t=$SECONDS
FIXED_JSON=$(pexec python3 /scripts/load_probe.py --base "$BASE" \
  --writers 12 --requests 20 --mode mixed --login-every 5 --label fixed)
T_LOAD_FIXED=$((SECONDS-t))
echo "$FIXED_JSON"

# ---------- audit trail ----------
EVENTS_TAIL=$(docker exec "$PROJ-dokku-1" sh -c 'tail -6 /var/log/dokku/events.log 2>/dev/null' || echo "(no events log)")

# ---------- judge + write results ----------
T_TOTAL=$((SECONDS-T_START))
set +e
python3 - "$FAULTY_JSON" "$FIXED_JSON" \
  "$T_UP" "$T_PROBE_PREP" "$T_PROVISION" "$T_FIX" "$T_LOAD_FAULTY" "$T_LOAD_FIXED" "$T_TOTAL" \
  "$RESULTS" "$FIXED_VAL" "$WORKERS_STARTED" "$APP" "$EVENTS_TAIL" <<'PYEOF'
import json, sys, datetime
faulty, fixed = json.loads(sys.argv[1]), json.loads(sys.argv[2])
t_up, t_probe, t_prov, t_fix, t_lf, t_lx, t_tot = map(int, sys.argv[3:10])
results, fixed_val, workers, app, events = sys.argv[10], sys.argv[11], sys.argv[12], sys.argv[13], sys.argv[14]
sep_p95 = faulty["p95_ms"] / max(fixed["p95_ms"], 1e-9)
sep_thr = fixed["throughput_rps"] / max(faulty["throughput_rps"], 1e-9)
ok = faulty["p95_ms"] > 2 * fixed["p95_ms"] and fixed["error_rate"] == 0
row = lambda r: f'| {r["label"]} | {r["throughput_rps"]} | {r["p50_ms"]} | {r["p95_ms"]} | {r["max_ms"]} | {r["errors"]}/{r["total_requests"]} |'
md = f"""# SMOKE-RESULTS — dokku plane + vendored Conduit SUT (measured)

Run: {datetime.datetime.now().isoformat(timespec='seconds')} · arm64 Docker Desktop ·
stack: `smoke-compose.yaml` (dokku 0.35.18 socket-sibling + postgres:16 + python probe) ·
SUT: vendored `nsidnev/fastapi-realworld-example-app` @ 029eb77 + `otel-wrap/` overlay ·
verdict: **{"PASS" if ok else "FAIL"}**

## Timings
| Phase | Wall time |
|---|---|
| compose up (dokku+postgres+probe) | {t_up}s |
| probe prep (apt openssh-client) | {t_probe}s |
| provision + FAULTY deploy (`git:sync --build`) | {t_prov}s |
| fix (`ssh config:set` -> rebuild -> healthy) | {t_fix}s |
| faulty load run | {t_lf}s |
| fixed load run | {t_lx}s |
| **total smoke** | **{t_tot}s** |

## The fault, measured through dokku (direct container-name path)
Workload: 12 concurrent writers x 20 iterations; each iteration = 1 write
(`POST /api/articles`) + 1 read (`GET /api/articles?limit=20`), plus a login
(bcrypt session churn) every 5th iteration. `{app}.web.1:8000`, probe sibling.

| Config | rps | p50 ms | p95 ms | max ms | errors |
|---|---|---|---|---|---|
{row(faulty)}
{row(fixed)}

Separation: **p95 x{sep_p95:.1f}**, throughput x{sep_thr:.1f}. Fault knob:
`WEB_CONCURRENCY` (faulty=1, fix=4) — see `../sut-conduit/otel-wrap/README.md`
for why the originally-hypothesized `MAX_CONNECTIONS_COUNT` pool knob was
measured and rejected.

## Verified along the way
- app healthy on **direct container name** before AND after the fix redeploy
  (the dokku nginx vhost proxy is not used, per the spike)
- login/create-article/read-back API round trip
- agent surface: `ssh dokku@dokku config:set/config:get` with the pre-generated
  agent key (`ssh-keys:add agent`); `config:get WEB_CONCURRENCY={fixed_val}`
  post-fix; uvicorn logged {workers} started worker processes
- deploy path: `dokku git:sync --build` from an in-container local git repo
  (no SSH needed for provisioning)
- `dokku events:on` audit trail tail:

```
{events}
```

## OTel
Smoke runs with `OTEL_SDK_DISABLED=true` (no collector in this stack, per plan —
the logfire receiver is wired at task-assembly). Instrumentation itself was
verified separately with a console exporter: FastAPI server spans
(`GET /api/articles`) + asyncpg client spans (19 `SELECT` spans for one list
page — the app's N+1 is visible). Enabling export is pure env:
`OTEL_SDK_DISABLED` off + `OTEL_EXPORTER_OTLP_ENDPOINT=http://<collector>:4318`.
"""
open(results, "w").write(md)
print(md)
sys.exit(0 if ok else 1)
PYEOF
RC=$?
set -e
say "smoke finished (rc=$RC) — results written to $RESULTS"
exit $RC

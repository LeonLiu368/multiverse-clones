#!/usr/bin/env bash
# Local smoke test for the two Jira-clone read tasks (native arm via amd64 emulation).
#
# For each task it:
#   1. builds the `main` agent image from the task's environment/Dockerfile
#   2. starts the `jira` sidecar (prod-v1, or empty + mounted state.json) on a docker network
#   3. starts `main` on the same network, waits for the sidecar
#   4. asserts ISOLATION: the agent has NO /var/lib/ticketvector/state.json on disk
#   5. NOP run   -> verifier must give reward 0 (no answer written)
#   6. ORACLE run (solve.sh) -> verifier must give reward 1
#
# The verifier (tests/test.sh) runs INSIDE the agent container, computing ground truth via the
# `jira` CLI over the network — exactly as Harbor would.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NET="jira-smoke-$$"
PASS=0; FAIL=0

log(){ echo "  $*"; }

run_task() {
  local task="$1" gateway_image="$2" state_mount="$3" gw_actor="${4:-agent}"
  local dir="$ROOT/tasks/$task"
  echo "============================================================"
  echo "TASK: $task   (gateway=$gateway_image)"
  echo "============================================================"
  local sc="jira-sc-$$" ag="jira-ag-$$" main_img="${task}-main:smoke"

  docker rm -f "$sc" "$ag" >/dev/null 2>&1 || true

  log "build main agent image"
  docker build --platform linux/amd64 -q -t "$main_img" \
    -f "$dir/environment/Dockerfile" "$dir/environment" >/dev/null || { echo "BUILD FAILED"; FAIL=$((FAIL+1)); return; }

  log "start jira sidecar"
  if [ -n "$state_mount" ]; then
    docker run -d --name "$sc" --network "$NET" --network-alias jira \
      -v "$dir/environment/data/state.json:/var/lib/ticketvector/state.json:ro" \
      -e "WORLD_ISSUES_ACTOR=$gw_actor" \
      "$gateway_image" >/dev/null
  else
    docker run -d --name "$sc" --network "$NET" --network-alias jira \
      -e "WORLD_ISSUES_ACTOR=$gw_actor" \
      "$gateway_image" >/dev/null
  fi
  local ok=0
  for _ in $(seq 1 30); do
    docker exec "$sc" python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8765/health',timeout=1)" >/dev/null 2>&1 && { ok=1; break; }
    sleep 1
  done
  [ "$ok" = 1 ] && log "sidecar healthy" || { echo "SIDECAR UNHEALTHY"; FAIL=$((FAIL+1)); docker rm -f "$sc" >/dev/null 2>&1; return; }

  log "start main agent"
  docker run -d --name "$ag" --network "$NET" \
    -e WORLD_ISSUES_BACKEND=remote -e WORLD_ISSUES_AGENT_MODE=1 -e WORLD_ISSUES_OUTPUT=json \
    -e WORLD_ISSUES_ACTOR=agent -e PLANE_BASE_URL=http://jira:8765 \
    "$main_img" >/dev/null
  sleep 3

  # ---- isolation check ----
  if docker exec "$ag" sh -c 'test -e /var/lib/ticketvector/state.json' 2>/dev/null; then
    echo "  ISOLATION FAIL: agent has /var/lib/ticketvector/state.json on disk"; FAIL=$((FAIL+1))
  else
    log "ISOLATION OK: agent has NO state.json on disk"
  fi
  # sanity: the agent CAN reach the data over the tool
  log "agent jira reachability: $(docker exec "$ag" sh -c 'jira issue list --json 2>/dev/null | head -c 60')..."

  # mount the task's tests + solution into the agent
  docker cp "$dir/tests/test.sh" "$ag:/test.sh" >/dev/null
  docker cp "$dir/solution/solve.sh" "$ag:/solve.sh" >/dev/null
  docker exec "$ag" sh -c 'mkdir -p /logs/verifier'

  # ---- NOP run -> reward 0 ----
  docker exec "$ag" sh -c 'rm -f /workspace/answer.txt /logs/verifier/reward.txt; bash /test.sh' >/tmp/nop.$$ 2>&1
  local nop; nop="$(docker exec "$ag" sh -c 'cat /logs/verifier/reward.txt 2>/dev/null')"
  if [ "$nop" = "0" ]; then log "NOP reward=0  OK"; else echo "  NOP reward=$nop  FAIL"; cat /tmp/nop.$$; FAIL=$((FAIL+1)); fi

  # ---- ORACLE run -> reward 1 ----
  docker exec "$ag" sh -c 'rm -f /logs/verifier/reward.txt; bash /solve.sh' >/tmp/orc.$$ 2>&1 || { echo "  ORACLE solve.sh errored"; cat /tmp/orc.$$; }
  docker exec "$ag" sh -c 'bash /test.sh' >/tmp/orcv.$$ 2>&1
  local orc; orc="$(docker exec "$ag" sh -c 'cat /logs/verifier/reward.txt 2>/dev/null')"
  if [ "$orc" = "1" ]; then log "ORACLE reward=1  OK"; PASS=$((PASS+1)); else echo "  ORACLE reward=$orc  FAIL"; cat /tmp/orcv.$$; FAIL=$((FAIL+1)); fi
  log "answer.txt: $(docker exec "$ag" sh -c 'cat /workspace/answer.txt 2>/dev/null' | tr '\n' '|')"

  docker rm -f "$sc" "$ag" >/dev/null 2>&1 || true
  rm -f /tmp/nop.$$ /tmp/orc.$$ /tmp/orcv.$$
}

docker network create "$NET" >/dev/null 2>&1 || true
trap 'docker network rm "$NET" >/dev/null 2>&1 || true' EXIT

run_task "jira-status-lookup"        "jira-gateway:prod-v1" ""      "agent"
run_task "jira-assignee-count"       "jira-gateway:empty"   "mount" "agent"
run_task "jira-transition-roundtrip" "jira-gateway:empty"   "mount" "priya.singh"

echo "============================================================"
echo "SMOKE SUMMARY: pass=$PASS fail=$FAIL"
[ "$FAIL" = 0 ] && echo "ALL GREEN" || echo "SOME FAILURES"
exit "$FAIL"

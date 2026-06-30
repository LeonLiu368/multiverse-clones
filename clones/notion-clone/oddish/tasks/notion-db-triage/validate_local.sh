#!/bin/bash
# Local (no-docker) nop/oracle check: boot the gateway against a fresh copy of the
# baked corpus, run the verifier on the untouched world (expect nop=0), then run the
# oracle solution and re-run the verifier (expect oracle=1). Run from the clone root
# inside the project venv.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"
. .venv/bin/activate

PORT=3791
CORPUS=/tmp/notion_task_corpus.db
cp notion_corpus.db "$CORPUS"
NOTION_DB="$CORPUS" uvicorn notionclone.api.app:app --host 127.0.0.1 --port $PORT >/tmp/task_uvicorn.log 2>&1 &
SRV=$!
trap "kill $SRV 2>/dev/null" EXIT
export NOTION_API_URL="http://127.0.0.1:$PORT"
export NOTION_TOKEN=notion-clone-token
export REWARD_DIR=/tmp/notion_reward
mkdir -p "$REWARD_DIR"
for i in $(seq 1 50); do curl -s "$NOTION_API_URL/health" >/dev/null 2>&1 && break; sleep 0.1; done

VER=oddish/tasks/notion-db-triage/tests/run_verifier.sh
SOLVE=oddish/tasks/notion-db-triage/solution/solve.sh

echo "== NOP (no agent action) =="
bash "$VER"; NOP=$(cat "$REWARD_DIR/reward.txt" 2>/dev/null)
echo "nop reward = $NOP"

echo "== ORACLE =="
bash "$SOLVE"
bash "$VER"; ORC=$(cat "$REWARD_DIR/reward.txt" 2>/dev/null)
echo "oracle reward = $ORC"

echo "RESULT: nop=$NOP oracle=$ORC"
[ "$NOP" = "0.0" ] && [ "$ORC" = "1.0" ] && echo "PASS: nop=0, oracle=1" || echo "FAIL"

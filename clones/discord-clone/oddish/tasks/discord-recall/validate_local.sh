#!/bin/bash
# Local (no-docker) nop/oracle check for the read-only recall task: boot the gateway
# against a fresh copy of the baked corpus, run the verifier on the empty workdir
# (expect nop=0 — no answer.txt), then run the oracle and re-run the verifier
# (expect oracle=1). Run from the clone root inside the project venv (.venv).
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"
. .venv/bin/activate

PORT=8792
CORPUS=/tmp/discord_recall_corpus.db
cp discord_corpus.db "$CORPUS"
DISCORD_DB="$CORPUS" uvicorn discordclone.api.app:app --host 127.0.0.1 --port $PORT >/tmp/disc_recall_uvicorn.log 2>&1 &
SRV=$!
trap "kill $SRV 2>/dev/null" EXIT
export DISCORD_API_URL="http://127.0.0.1:$PORT"
export DISCORD_BOT_TOKEN=discord-clone-token
export REWARD_DIR=/tmp/discord_recall_reward
mkdir -p "$REWARD_DIR"

# Empty scratch workdir (as the agent container starts).
export WORKDIR=/tmp/discord_recall_workspace
rm -rf "$WORKDIR"; mkdir -p "$WORKDIR"

for i in $(seq 1 50); do curl -s "$DISCORD_API_URL/health" >/dev/null 2>&1 && break; sleep 0.1; done

VER=oddish/tasks/discord-recall/tests/run_verifier.sh
SOLVE=oddish/tasks/discord-recall/solution/solve.sh

echo "== NOP (no agent action) =="
bash "$VER"; NOP=$(cat "$REWARD_DIR/reward.txt" 2>/dev/null)
echo "nop reward = $NOP"

echo "== ORACLE =="
bash "$SOLVE"
bash "$VER"; ORC=$(cat "$REWARD_DIR/reward.txt" 2>/dev/null)
echo "oracle reward = $ORC"

echo "RESULT: nop=$NOP oracle=$ORC"
[ "$NOP" = "0.0" ] && [ "$ORC" = "1.0" ] && echo "PASS: nop=0, oracle=1" || { echo "FAIL"; exit 1; }

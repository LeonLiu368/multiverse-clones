#!/bin/bash
# Oracle solution: recover the agreed rate limit + burst from the #engineering
# discussion via the discord CLI, DERIVE the numbers from the tool output (parse,
# don't hardcode), and write them to /workspace/answer.txt. Read-only: no code fix,
# no writes back to Discord. Uses only the agent tools over the API.
set -euo pipefail
export DISCORD_API_URL="${DISCORD_API_URL:-http://discord:8080}"
WORKDIR="${WORKDIR:-/workspace}"

# 1. resolve the guild the bot is in.
GID=$(discord users guilds | python3 -c 'import json,sys; print(json.load(sys.stdin)[0]["id"])')

# 2. locate the #engineering channel id (list guild channels).
ECID=$(discord guilds channels "$GID" \
       | python3 -c 'import json,sys; print(next(c["id"] for c in json.load(sys.stdin) if c["name"]=="engineering"))')

# 3. read the #engineering history AND cross-check via guild search, then DERIVE the
#    agreed rate + burst from whichever tool surfaces the decision message. We parse
#    both "<N> requests/min" and "burst of <N>" out of the recovered content — no bare
#    120/20 literal appears in this oracle.
HIST=$(discord channels messages "$ECID" --limit 100)
SEARCH=$(discord guilds search "$GID" --content "requests/min")

DERIVED=$(HIST="$HIST" SEARCH="$SEARCH" python3 - <<'PY'
import json, os, re, sys

def contents(blob):
    blob = (blob or "").strip()
    if not blob:
        return []
    data = json.loads(blob)
    # channel history -> list[msg]; guild search -> {"messages": [[msg], ...]}
    if isinstance(data, dict) and "messages" in data:
        return [hit[0].get("content", "") for hit in data["messages"]]
    if isinstance(data, list):
        return [m.get("content", "") for m in data]
    return []

rate = burst = None
for c in contents(os.environ.get("HIST")) + contents(os.environ.get("SEARCH")):
    mr = re.search(r"(\d+)\s*requests\s*/\s*min", c, re.I)
    mb = re.search(r"burst\s+of\s+(\d+)", c, re.I)
    if mr and mb:
        rate, burst = mr.group(1), mb.group(1)
        break

if rate is None or burst is None:
    sys.exit("oracle: could not recover rate/burst from #engineering discussion")
print(rate, burst)
PY
)

RATE=$(echo "$DERIVED" | awk '{print $1}')
BURST=$(echo "$DERIVED" | awk '{print $2}')
: "${RATE:?}" "${BURST:?}"

# 4. write the recovered answer (the graded artifact).
mkdir -p "$WORKDIR"
printf 'rate=%s\nburst=%s\n' "$RATE" "$BURST" > "$WORKDIR/answer.txt"

echo "oracle: recovered rate=$RATE burst=$BURST -> $WORKDIR/answer.txt"

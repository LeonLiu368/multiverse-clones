#!/bin/bash
# Oracle solution: recover the agreed TTL from the incident discussion via the
# discord CLI, fix the config, and post the remediation notice to #deploys. Uses
# only the agent tools over the API (no disk access to the corpus).
set -euo pipefail
export DISCORD_API_URL="${DISCORD_API_URL:-http://discord:8080}"
WORKDIR="${WORKDIR:-/workspace}"

# 1. resolve the guild the bot is in.
GID=$(discord users guilds | python3 -c 'import json,sys; print(json.load(sys.stdin)[0]["id"])')

# 2. recover the agreed TTL from the incident decision (search the guild).
TTL=$(discord guilds search "$GID" --content "PRICING_CACHE_TTL" \
      | python3 -c '
import json,sys,re
d=json.load(sys.stdin)
for hit in d["messages"]:
    m=re.search(r"PRICING_CACHE_TTL back to (\d+)", hit[0]["content"])
    if m: print(m.group(1)); break
')
: "${TTL:?could not recover agreed TTL from incident discussion}"

# 3. apply the fix to the codebase.
python3 - "$WORKDIR/checkout-service/config.py" "$TTL" <<'PY'
import re, sys
path, ttl = sys.argv[1], sys.argv[2]
src = open(path).read()
src = re.sub(r"(?m)^(\s*PRICING_CACHE_TTL\s*=\s*)\d+", r"\g<1>" + ttl, src)
open(path, "w").write(src)
PY

# 4. find #deploys and post the remediation notice (the write half of the round-trip).
DEP=$(discord guilds channels "$GID" \
      | python3 -c 'import json,sys; print(next(c["id"] for c in json.load(sys.stdin) if c["name"]=="deploys"))')
discord channels send "$DEP" -m "INC-4471 remediation: restored PRICING_CACHE_TTL=$TTL and redeployed checkout-service." >/dev/null

echo "oracle: fixed config (TTL=$TTL) and posted remediation to #deploys"

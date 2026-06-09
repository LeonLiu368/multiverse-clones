#!/usr/bin/env bash
# Verifier for requests-json-nan.
# Reward 1 iff: the fix PR was merged AND requests/models.py on main contains
# allow_nan=False AND requests/exceptions.py on main defines InvalidJSONError.
set -uo pipefail

LOG_DIR="/logs/verifier"
mkdir -p "$LOG_DIR" 2>/dev/null || LOG_DIR="${TMPDIR:-/tmp}/verifier"
mkdir -p "$LOG_DIR" 2>/dev/null || true
VERIFIER_DIR="/verifier"
mkdir -p "$VERIFIER_DIR" 2>/dev/null || VERIFIER_DIR=""

write_reward() {
  local v="$1"
  echo "$v" > reward.txt 2>/dev/null || true
  echo "$v" > "$LOG_DIR/reward.txt" 2>/dev/null || true
  [ -n "$VERIFIER_DIR" ] && echo "$v" > "$VERIFIER_DIR/reward.txt" 2>/dev/null || true
}
write_reward 0

R=acme/api-service
py() { python3 -c "$1" 2>/dev/null || echo ""; }

# 1. requests/models.py on main must pass allow_nan=False to json.dumps
models_fixed=0
for _ in $(seq 1 10); do
  raw=$(gh api "repos/$R/contents/requests/models.py?ref=main" 2>/dev/null)
  [ -z "$raw" ] && { sleep 2; continue; }
  content=$(echo "$raw" | py 'import sys,json,base64; d=json.load(sys.stdin); print(base64.b64decode(d["content"]).decode())')
  if echo "$content" | grep -q 'allow_nan=False'; then
    models_fixed=1
  fi
  break
done

# 2. requests/exceptions.py on main must define InvalidJSONError
exceptions_fixed=0
for _ in $(seq 1 10); do
  raw=$(gh api "repos/$R/contents/requests/exceptions.py?ref=main" 2>/dev/null)
  [ -z "$raw" ] && { sleep 2; continue; }
  content=$(echo "$raw" | py 'import sys,json,base64; d=json.load(sys.stdin); print(base64.b64decode(d["content"]).decode())')
  if echo "$content" | grep -q 'class InvalidJSONError'; then
    exceptions_fixed=1
  fi
  break
done

# 3. A PR targeting main must be merged (not just closed)
merged=0
for _ in $(seq 1 10); do
  merged_raw=$(gh api "repos/$R/pulls?state=closed&base=main" 2>/dev/null)
  [ -z "$merged_raw" ] && { sleep 2; continue; }
  merged=$(echo "$merged_raw" | py 'import sys,json; xs=json.load(sys.stdin); print(int(any(x.get("merged") for x in xs)))')
  merged=${merged:-0}
  break
done

ok=0
[ "${models_fixed:-0}" = 1 ] && \
[ "${exceptions_fixed:-0}" = 1 ] && \
[ "${merged:-0}" = 1 ] && ok=1

write_reward "$ok"
echo "models_fixed=$models_fixed exceptions_fixed=$exceptions_fixed pr_merged=$merged -> $ok"

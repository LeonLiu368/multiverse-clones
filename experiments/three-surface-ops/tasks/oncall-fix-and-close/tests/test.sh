#!/usr/bin/env bash
# Verifier for oncall-fix-and-close (PR-review task).
# Reward 1 iff: the fix PR was merged into main AND search.py on main now
# handles an empty term correctly.
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

R=acme/webapp
py() { python3 -c "$1" 2>/dev/null || echo ""; }

# 1. search.py on main handles empty term (retry briefly for API readiness)
fixed=0
for _ in $(seq 1 10); do
  raw=$(gh api "repos/$R/contents/search.py?ref=main" 2>/dev/null)
  [ -z "$raw" ] && { sleep 2; continue; }
  content=$(echo "$raw" | py 'import sys,json,base64; d=json.load(sys.stdin); print(base64.b64decode(d["content"]).decode())')
  echo "$content" > /tmp/search_check.py
  fixed=$(python3 - << 'PYEOF'
try:
    code = open("/tmp/search_check.py").read()
    if not code.strip():
        print(0)
    else:
        g = {}
        exec(code, g)
        print(1 if g["search_users"]("") == [] else 0)
except Exception:
    print(0)
PYEOF
)
  break
done

# 2. A PR targeting main must be merged
merged=0
for _ in $(seq 1 10); do
  merged_raw=$(gh api "repos/$R/pulls?state=closed&base=main" 2>/dev/null)
  [ -z "$merged_raw" ] && { sleep 2; continue; }
  merged=$(echo "$merged_raw" | py 'import sys,json; xs=json.load(sys.stdin); print(int(any(x.get("merged") for x in xs)))')
  merged=${merged:-0}
  break
done

ok=0
[ "${fixed:-0}" = 1 ] && [ "${merged:-0}" = 1 ] && ok=1
write_reward "$ok"
echo "search_fixed=$fixed pr_merged=$merged -> $ok"

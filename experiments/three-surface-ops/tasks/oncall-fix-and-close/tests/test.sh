#!/usr/bin/env bash
# Verifier for oncall-fix-and-close.
# Reward 1 iff: search.py on main handles empty term correctly AND a PR was merged.
set -uo pipefail
mkdir -p /logs/verifier 2>/dev/null || true

R=acme/webapp
py() { python3 -c "$1" 2>/dev/null || echo ""; }

# 1. Fetch search.py on main and test it handles empty term
raw=$(gh api "repos/$R/contents/search.py?ref=main" 2>/dev/null)
if [ -z "$raw" ]; then
  fixed=0
else
  content=$(echo "$raw" | py 'import sys,json,base64; d=json.load(sys.stdin); print(base64.b64decode(d["content"]).decode())')
  echo "$content" > /tmp/search_check.py
  fixed=$(python3 - << 'PYEOF'
import sys
try:
    code = open("/tmp/search_check.py").read()
    if not code.strip():
        print(0)
    else:
        g = {}
        exec(code, g)
        result = g["search_users"]("")
        print(1 if result == [] else 0)
except Exception:
    print(0)
PYEOF
)
fi

# 2. A PR targeting main must be merged
merged_raw=$(gh api "repos/$R/pulls?state=closed&base=main" 2>/dev/null)
if [ -z "$merged_raw" ]; then
  merged=0
else
  merged=$(echo "$merged_raw" | py 'import sys,json; xs=json.load(sys.stdin); print(int(any(x.get("merged") for x in xs)))')
  merged=${merged:-0}
fi

ok=0
[ "${fixed:-0}" = 1 ] && [ "${merged:-0}" = 1 ] && ok=1
echo $ok > /logs/verifier/reward.txt 2>/dev/null || true
echo "search_fixed=$fixed pr_merged=$merged -> $ok"

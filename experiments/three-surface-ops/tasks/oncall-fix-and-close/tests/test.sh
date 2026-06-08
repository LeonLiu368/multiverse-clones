#!/usr/bin/env bash
# Verifier for oncall-fix-and-close.
# Reward 1 iff: search.py on main handles empty term correctly AND a PR was merged.
set -uo pipefail
mkdir -p /logs/verifier

R=acme/webapp
py() { python3 -c "$1" 2>/dev/null || echo 0; }

# 1. Fetch search.py on main and test it handles empty term
content=$(gh api "repos/$R/contents/search.py?ref=main" 2>/dev/null \
  | py 'import sys,json,base64; d=json.load(sys.stdin); print(base64.b64decode(d["content"]).decode())')

echo "$content" > /tmp/search_check.py

fixed=$(python3 - <<'PYEOF'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("search_check", "/tmp/search_check.py")
mod = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(mod)
    result = mod.search_users("")
    print(1 if result == [] else 0)
except Exception as e:
    print(0)
PYEOF
)

# 2. A PR targeting main must be merged
merged=$(gh api "repos/$R/pulls?state=closed&base=main" 2>/dev/null \
  | py 'import sys,json; xs=json.load(sys.stdin); print(int(any(x.get("merged") for x in xs)))')

ok=0
[ "$fixed" = 1 ] && [ "$merged" = 1 ] && ok=1
echo $ok > /logs/verifier/reward.txt
echo "search_fixed=$fixed pr_merged=$merged -> $ok"

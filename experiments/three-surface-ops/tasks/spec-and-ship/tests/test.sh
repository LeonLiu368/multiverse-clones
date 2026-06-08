#!/usr/bin/env bash
# Verifier for spec-and-ship.
# Reward 1 iff: register.py on main has email validation AND a PR was merged.
set -uo pipefail
mkdir -p /logs/verifier 2>/dev/null || true

R=acme/platform
py() { python3 -c "$1" 2>/dev/null || echo ""; }

# 1. register.py must exist and pass behavioral email validation test
raw=$(gh api "repos/$R/contents/register.py?ref=main" 2>/dev/null)
if [ -z "$raw" ]; then
  validated=0
else
  content=$(echo "$raw" | py 'import sys,json,base64; d=json.load(sys.stdin); print(base64.b64decode(d["content"]).decode())')
  if [ -z "$content" ]; then
    validated=0
  else
    echo "$content" > /tmp/register_check.py
    validated=$(python3 - << 'PYEOF'
import builtins
try:
    code = open("/tmp/register_check.py").read()
    if not code.strip():
        print(0)
    else:
        class DB:
            def create(self, d): return {"id": 1, **d}
        g = {"db": DB(), "__builtins__": builtins}
        exec(code, g)
        create_user = g["create_user"]
        r1 = create_user("notanemail", "pw")
        r2 = create_user("valid@example.com", "pw")
        ok = (isinstance(r1, tuple) and r1[1] not in (201, 200)) and (isinstance(r2, tuple) and r2[1] == 201)
        print(1 if ok else 0)
except Exception:
    print(0)
PYEOF
)
  fi
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
[ "${validated:-0}" = 1 ] && [ "${merged:-0}" = 1 ] && ok=1
echo $ok > /logs/verifier/reward.txt 2>/dev/null || true
echo "email_validated=$validated pr_merged=$merged -> $ok"

#!/usr/bin/env bash
set -uo pipefail
mkdir -p /logs/verifier

R=acme/platform
py() { python3 -c "$1" 2>/dev/null || echo 0; }

# 1. register.py on main must contain email regex validation
content=$(gh api "repos/$R/contents/register.py?ref=main" 2>/dev/null \
  | py 'import sys,json,base64; d=json.load(sys.stdin); print(base64.b64decode(d["content"]).decode())')

# Check for email validation pattern (regex compile or re.match with @)
if echo "$content" | grep -qE 'compile|match.*@|@.*match'; then has_validation=1; else has_validation=0; fi

# Also behaviorally test it
echo "$content" > /tmp/register_check.py
validated=$(python3 - <<'PYEOF'
import builtins

try:
    code = open("/tmp/register_check.py").read()

    class DB:
        def create(self, d): return {"id": 1, **d}

    g = {"db": DB(), "__builtins__": builtins}
    exec(code, g)
    create_user = g["create_user"]
    r1 = create_user("notanemail", "pw")
    r2 = create_user("valid@example.com", "pw")
    # r1 should be error (422 or 400), r2 should be success (201)
    ok = (isinstance(r1, tuple) and r1[1] != 201) and (isinstance(r2, tuple) and r2[1] == 201)
    print(1 if ok else 0)
except Exception as e:
    print(0)
PYEOF
)

# 2. PR merged
merged=$(gh api "repos/$R/pulls?state=closed&base=main" 2>/dev/null \
  | py 'import sys,json; xs=json.load(sys.stdin); print(int(any(x.get("merged") for x in xs)))')

ok=0
[ "${validated:-0}" = 1 ] && [ "$merged" = 1 ] && ok=1
echo $ok > /logs/verifier/reward.txt
echo "email_validated=$validated pr_merged=$merged -> $ok"

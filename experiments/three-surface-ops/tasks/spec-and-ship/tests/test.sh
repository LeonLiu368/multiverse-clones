#!/usr/bin/env bash
# Verifier for spec-and-ship (PR-review task).
# Reward 1 iff: the feature PR was merged into main AND register.py on main
# passes the behavioral email-validation test.
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

R=acme/platform
py() { python3 -c "$1" 2>/dev/null || echo ""; }

# 1. register.py on main passes behavioral email validation (retry for readiness)
validated=0
for _ in $(seq 1 10); do
  raw=$(gh api "repos/$R/contents/register.py?ref=main" 2>/dev/null)
  [ -z "$raw" ] && { sleep 2; continue; }
  content=$(echo "$raw" | py 'import sys,json,base64; d=json.load(sys.stdin); print(base64.b64decode(d["content"]).decode())')
  [ -z "$content" ] && { validated=0; break; }
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
[ "${validated:-0}" = 1 ] && [ "${merged:-0}" = 1 ] && ok=1
write_reward "$ok"
echo "email_validated=$validated pr_merged=$merged -> $ok"

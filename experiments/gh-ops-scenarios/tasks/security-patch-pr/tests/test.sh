#!/usr/bin/env bash
# Verifier for security-patch-pr.
# Reward 1 iff: search.py on main no longer uses f-string SQL, a PR was merged,
# and issue #1 is closed.
set -uo pipefail
mkdir -p /logs/verifier

R=acme/api-service
py() { python3 -c "$1" 2>/dev/null || echo 0; }

# 1. search.py on main must not contain the vulnerable f-string pattern.
content=$(gh api "repos/$R/contents/search.py?ref=main" 2>/dev/null \
  | py 'import sys,json,base64; d=json.load(sys.stdin); print(base64.b64decode(d["content"]).decode())')
if echo "$content" | grep -qE "f['\"]SELECT"; then
  fixed=0
else
  fixed=1
fi

# 2. A PR targeting main must be merged.
merged=$(gh api "repos/$R/pulls?state=closed&base=main" 2>/dev/null \
  | py 'import sys,json; xs=json.load(sys.stdin); print(int(any(x.get("merged") for x in xs)))')

# 3. Issue #1 must be closed.
issue_closed=$(gh api "repos/$R/issues/1" 2>/dev/null \
  | py 'import sys,json; print(int(json.load(sys.stdin).get("state")=="closed"))' || echo 0)

ok=0
[ "$fixed" = 1 ] && [ "$merged" = 1 ] && [ "$issue_closed" = 1 ] && ok=1
echo $ok > /logs/verifier/reward.txt
echo "fixed=$fixed merged=$merged issue_closed=$issue_closed -> $ok"

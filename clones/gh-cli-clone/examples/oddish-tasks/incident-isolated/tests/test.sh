#!/usr/bin/env bash
set -uo pipefail; mkdir -p /logs/verifier
R=acme/webapp
py(){ python3 -c "$1" 2>/dev/null || echo 0; }

# --- R6.3 isolation guard (runs in the agent; mirrors tests/test_isolation.py) ---
# The agent must be a sealed, data-free client: no forge state on disk, the clone
# source/generator not importable, no api/seed source present. A leak here means
# the answer is readable/recomputable locally and the task is invalid — fail hard.
iso_fail=0
for p in /var/lib/forgejo /shared/token /opt/ghclone; do
  [ -e "$p" ] && { echo "ISOLATION LEAK: $p present on agent"; iso_fail=1; }
done
python3 -c 'import ghclone' >/dev/null 2>&1 && { echo "ISOLATION LEAK: import ghclone succeeds on agent"; iso_fail=1; }
if [ "$iso_fail" = 1 ]; then echo 0 >/logs/verifier/reward.txt; echo "isolation check failed -> 0"; exit 0; fi

gh api "repos/$R/contents/billing.py?ref=main" 2>/dev/null | py 'import sys,json,base64;open("/tmp/b.py","w").write(base64.b64decode(json.load(sys.stdin)["content"]).decode())'
fixed=$(python3 -c 'import sys;sys.path.insert(0,"/tmp");import b;assert b.split_bill(100,0)==0;assert b.split_bill(100,4)==25' >/dev/null 2>&1 && echo 1 || echo 0)
merged=$(gh api "repos/$R/pulls?state=all&limit=50" 2>/dev/null | py 'import sys,json;xs=json.load(sys.stdin);print(int(bool(xs) and xs[0].get("merged")))')
closed=$(gh api "repos/$R/issues?type=issues&state=all&limit=50" 2>/dev/null | py 'import sys,json;print(int(any("Incident" in i["title"] and i["state"]=="closed" for i in json.load(sys.stdin))))')
ok=0; [ "$fixed" = 1 ] && [ "$merged" = 1 ] && [ "$closed" = 1 ] && ok=1
echo $ok >/logs/verifier/reward.txt
echo "fixed=$fixed merged=$merged incident_closed=$closed -> $ok"

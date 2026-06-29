#!/usr/bin/env bash
set -uo pipefail; mkdir -p /logs/verifier
R=acme/webapp
py(){ python3 -c "$1" 2>/dev/null || echo 0; }
gh api "repos/$R/contents/billing.py?ref=main" 2>/dev/null | py 'import sys,json,base64;open("/tmp/b.py","w").write(base64.b64decode(json.load(sys.stdin)["content"]).decode())'
fixed=$(python3 -c 'import sys;sys.path.insert(0,"/tmp");import b;assert b.split_bill(100,0)==0;assert b.split_bill(100,4)==25' >/dev/null 2>&1 && echo 1 || echo 0)
merged=$(gh api "repos/$R/pulls?state=all&limit=50" 2>/dev/null | py 'import sys,json;xs=json.load(sys.stdin);print(int(bool(xs) and xs[0].get("merged")))')
closed=$(gh api "repos/$R/issues?type=issues&state=all&limit=50" 2>/dev/null | py 'import sys,json;print(int(any("Incident" in i["title"] and i["state"]=="closed" for i in json.load(sys.stdin))))')
ok=0; [ "$fixed" = 1 ] && [ "$merged" = 1 ] && [ "$closed" = 1 ] && ok=1
echo $ok >/logs/verifier/reward.txt
echo "fixed=$fixed merged=$merged incident_closed=$closed -> $ok"

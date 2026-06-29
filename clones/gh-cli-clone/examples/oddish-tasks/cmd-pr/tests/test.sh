#!/usr/bin/env bash
set -uo pipefail; mkdir -p /logs/verifier
py(){ python3 -c "$1" 2>/dev/null || echo 0; }
fork_ok=$(gh repo view team/svc >/dev/null 2>&1 && echo 1 || echo 0)
prs=$(gh api "repos/acme/svc/pulls?state=all&limit=50" 2>/dev/null)
num=$(echo "$prs" | py 'import sys,json;xs=json.load(sys.stdin);print(xs[0]["number"] if xs else 0)')
merged=$(echo "$prs" | py 'import sys,json;xs=json.load(sys.stdin);print(int(bool(xs) and xs[0].get("merged")))')
head=$(echo "$prs" | py 'import sys,json;xs=json.load(sys.stdin);print(xs[0]["head"]["ref"] if xs else "")')
behaves=0
if [ -n "$head" ]; then
  gh api "repos/acme/svc/contents/calc.py?ref=main" 2>/dev/null | py 'import sys,json,base64;open("/tmp/c.py","w").write(base64.b64decode(json.load(sys.stdin)["content"]).decode())'
  python3 -c 'import sys;sys.path.insert(0,"/tmp");import c;assert c.div(1,0)==0;assert c.div(6,2)==3' 2>/dev/null && behaves=1
fi
nrev=$(gh api repos/acme/svc/pulls/$num/reviews 2>/dev/null | py 'import sys,json;print(len(json.load(sys.stdin)))')
iss_closed=$(gh api "repos/acme/svc/issues/1" 2>/dev/null | py 'import sys,json;print(int(json.load(sys.stdin).get("state")=="closed"))')
ok=0
[ "$fork_ok" = 1 ] && [ "$merged" = 1 ] && [ "$behaves" = 1 ] && [ "${nrev:-0}" -ge 1 ] && [ "$iss_closed" = 1 ] && ok=1
echo $ok > /logs/verifier/reward.txt
echo "fork=$fork_ok merged=$merged behaves=$behaves reviews=$nrev issue_closed=$iss_closed -> $ok"

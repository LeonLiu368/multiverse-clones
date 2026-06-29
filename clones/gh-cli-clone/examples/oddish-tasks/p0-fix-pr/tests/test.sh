#!/usr/bin/env bash
set -uo pipefail; mkdir -p /logs/verifier
reward=0
head=$(gh api "repos/acme/fixme/pulls?state=all&limit=50" 2>/dev/null | python3 -c 'import sys,json;xs=json.load(sys.stdin);print(xs[0]["head"]["ref"] if xs else "")' 2>/dev/null || echo "")
if [ -n "$head" ]; then
  gh api "repos/acme/fixme/contents/calc.py?ref=$head" 2>/dev/null | python3 -c 'import sys,json,base64;open("/tmp/calc.py","w").write(base64.b64decode(json.load(sys.stdin)["content"]).decode())' 2>/dev/null
  python3 -c 'import sys;sys.path.insert(0,"/tmp");import calc;assert calc.div(1,0)==0;assert calc.div(6,2)==3' 2>/dev/null && reward=1
fi
echo $reward >/logs/verifier/reward.txt
echo "head=$head reward=$reward"

#!/usr/bin/env bash
# Pass iff a PR exists whose head-branch calc.py actually BEHAVES correctly:
# div(1,0)==0 and div(6,2)==3. Behavior-based (not string-matching) so any
# correct fix passes, not just the oracle's exact phrasing.
set -uo pipefail; mkdir -p /logs/verifier
reward=0
head=$(gh pr list -R ghc-admin/fixme --state all --json 2>/dev/null \
       | python3 -c 'import sys,json;xs=json.load(sys.stdin);print(xs[0]["head"]["ref"] if xs else "")' 2>/dev/null || echo "")
if [ -n "$head" ]; then
  gh api "repos/ghc-admin/fixme/contents/calc.py?ref=$head" 2>/dev/null \
    | python3 -c 'import sys,json,base64;open("/tmp/calc.py","w").write(base64.b64decode(json.load(sys.stdin)["content"]).decode())' 2>/dev/null
  if python3 -c 'import sys;sys.path.insert(0,"/tmp");import calc;assert calc.div(1,0)==0;assert calc.div(6,2)==3' 2>/dev/null; then
    reward=1
  fi
fi
echo $reward > /logs/verifier/reward.txt
echo "head=$head reward=$reward"

#!/usr/bin/env bash
set -uo pipefail; mkdir -p /logs/verifier
R=acme/api
py(){ python3 -c "$1" 2>/dev/null || echo 0; }
head=$(gh api "repos/$R/pulls?state=all&limit=50" 2>/dev/null | py 'import sys,json;xs=json.load(sys.stdin);print(xs[0]["head"]["ref"] if xs else "")')
bumped=0
if [ -n "$head" ]; then
  req=$(gh api "repos/$R/contents/requirements.txt?ref=$head" 2>/dev/null | py 'import sys,json,base64;print(base64.b64decode(json.load(sys.stdin)["content"]).decode())')
  echo "$req" | python3 -c 'import sys,re;t=sys.stdin.read();m=re.search(r"requests==([0-9.]+)",t);v=m.group(1) if m else "0";print(v);import sys as s' >/tmp/v 2>/dev/null
  V=$(echo "$req" | grep -oE 'requests==[0-9.]+' | grep -oE '[0-9.]+$')
  python3 -c "import sys;from packaging.version import parse" 2>/dev/null && cmp=$(python3 -c "print(int(tuple(map(int,'$V'.split('.')))>= (2,31,0)))" 2>/dev/null) || cmp=$(python3 -c "print(int(tuple(map(int,'$V'.split('.')))>=(2,31,0)))" 2>/dev/null)
  [ "${cmp:-0}" = 1 ] && bumped=1
fi
issue=$(gh api "repos/$R/issues?type=issues&state=all&limit=50" 2>/dev/null | py 'import sys,json;print(int(any("CVE-2023-32681" in (i["title"]+i.get("body","")) for i in json.load(sys.stdin))))')
ok=0; [ "$bumped" = 1 ] && [ "$issue" = 1 ] && ok=1
echo $ok >/logs/verifier/reward.txt
echo "bumped=$bumped tracking_issue=$issue -> $ok"

#!/usr/bin/env bash
set -uo pipefail; mkdir -p /logs/verifier
R=acme/webapp2
py(){ python3 -c "$1" 2>/dev/null || echo 0; }
iss_closed=$(gh api "repos/$R/issues?type=issues&state=all&limit=50" 2>/dev/null | py 'import sys,json;print(int(any("blocker" in i["title"].lower() and i["state"]=="closed" for i in json.load(sys.stdin))))')
ms_closed=$(gh api "repos/$R/milestones?state=all" 2>/dev/null | py 'import sys,json;print(int(any(m["title"]=="v1.0" and m["state"]=="closed" for m in json.load(sys.stdin))))')
rel=$(gh api repos/$R/releases 2>/dev/null | py 'import sys,json;print(int(any(r["tag_name"]=="v1.0" for r in json.load(sys.stdin))))')
ok=0; [ "$iss_closed" = 1 ] && [ "$ms_closed" = 1 ] && [ "$rel" = 1 ] && ok=1
echo $ok >/logs/verifier/reward.txt
echo "blocker_closed=$iss_closed milestone_closed=$ms_closed release=$rel -> $ok"

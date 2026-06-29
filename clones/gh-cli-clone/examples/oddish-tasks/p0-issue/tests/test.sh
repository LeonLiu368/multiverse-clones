#!/usr/bin/env bash
set -uo pipefail; mkdir -p /logs/verifier
ok=$(gh api "repos/acme/app/issues?type=issues&state=all&limit=50" 2>/dev/null | python3 -c '
import sys,json
xs=json.load(sys.stdin)
m=[i for i in xs if i.get("title")=="TASK-DONE" and i.get("state")=="closed"]
print(1 if m else 0)
' 2>/dev/null || echo 0)
# also require a comment on it
nc=0
if [ "$ok" = "1" ]; then
  num=$(gh api "repos/acme/app/issues?type=issues&state=all&limit=50" 2>/dev/null | python3 -c 'import sys,json;print([i["number"] for i in json.load(sys.stdin) if i.get("title")=="TASK-DONE"][0])')
  nc=$(gh api repos/acme/app/issues/$num/comments 2>/dev/null | python3 -c 'import sys,json;print(len(json.load(sys.stdin)))' 2>/dev/null || echo 0)
fi
[ "$ok" = "1" ] && [ "${nc:-0}" -ge 1 ] && echo 1 >/logs/verifier/reward.txt || echo 0 >/logs/verifier/reward.txt
echo "closed_titled=$ok comments=$nc -> $(cat /logs/verifier/reward.txt)"

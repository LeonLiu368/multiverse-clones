#!/usr/bin/env bash
set -uo pipefail; mkdir -p /logs/verifier
R=acme/svc
py(){ python3 -c "$1" 2>/dev/null || echo 0; }

# end-state markers spanning every command group (verified independently via gh)
desc=$(gh api "repos/$R" 2>/dev/null | py 'import sys,json;print(int(json.load(sys.stdin).get("description")=="coverage-edited"))')
label=$(gh label list -R $R 2>/dev/null | grep -c "audit")
inc_closed=$(gh api "repos/$R/issues?type=issues&state=all&limit=50" 2>/dev/null | py 'import sys,json;print(int(any(i["title"]=="Coverage incident" and i["state"]=="closed" for i in json.load(sys.stdin))))')
track_open=$(gh api "repos/$R/issues?type=issues&state=all&limit=50" 2>/dev/null | py 'import sys,json;print(int(any("Track:" in i["title"] and i["state"]=="open" for i in json.load(sys.stdin))))')
merged=$(gh api "repos/$R/pulls?state=all&limit=50" 2>/dev/null | py 'import sys,json;print(int(any(p.get("merged") and p["title"]=="Add subtract" for p in json.load(sys.stdin))))')
release=$(gh release list -R $R 2>/dev/null | grep -c "v9.9")
artifact_issue=$(gh api "repos/$R/issues?type=issues&state=all&limit=50" 2>/dev/null | py 'import sys,json;print(int(any(i["title"].startswith("COVCODE-") for i in json.load(sys.stdin))))')

ok=0
[ "$desc" = 1 ] && [ "$label" -ge 1 ] && [ "$inc_closed" = 1 ] && [ "$track_open" = 1 ] \
  && [ "$merged" = 1 ] && [ "$release" -ge 1 ] && [ "$artifact_issue" = 1 ] && ok=1
echo $ok >/logs/verifier/reward.txt
echo "desc=$desc label=$label inc_closed=$inc_closed track_open=$track_open merged=$merged release=$release artifact_issue=$artifact_issue -> $ok"

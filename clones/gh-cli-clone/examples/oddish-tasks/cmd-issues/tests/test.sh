#!/usr/bin/env bash
set -uo pipefail; mkdir -p /logs/verifier
R=acme/tracker-v2
py(){ python3 -c "$1" 2>/dev/null || echo 0; }
renamed=$(gh api "repos/$R" 2>/dev/null | py 'import sys,json;print(1 if json.load(sys.stdin).get("name")=="tracker-v2" else 0)')
labels=$(gh api "repos/$R/labels" 2>/dev/null)
has_bug=$(echo "$labels" | py 'import sys,json;print(int(any(l["name"]=="bug" for l in json.load(sys.stdin))))')
no_dup=$(echo "$labels" | py 'import sys,json;print(int(not any(l["name"]=="duplicate" for l in json.load(sys.stdin))))')
has_ms=$(gh api "repos/$R/milestones" 2>/dev/null | py 'import sys,json;print(int(any(m["title"]=="v1.0" for m in json.load(sys.stdin))))')
iss=$(gh api "repos/$R/issues?type=issues&state=all&limit=50" 2>/dev/null)
issue_ok=$(echo "$iss" | py 'import sys,json;xs=json.load(sys.stdin);print(int(any(i["title"]=="Login fails on Safari" and i["state"]=="open" for i in xs)))')
num=$(echo "$iss" | py 'import sys,json;print([i["number"] for i in json.load(sys.stdin) if i["title"]=="Login fails on Safari"][0])')
ncom=$(gh api repos/$R/issues/$num/comments 2>/dev/null | py 'import sys,json;print(len(json.load(sys.stdin)))')
nreact=$(gh api repos/$R/issues/$num/reactions 2>/dev/null | py 'import sys,json;print(len(json.load(sys.stdin)))')
scratch_gone=$(gh repo view acme/scratch >/dev/null 2>&1 && echo 0 || echo 1)
ok=0
[ "$renamed" = 1 ] && [ "$has_bug" = 1 ] && [ "$no_dup" = 1 ] && [ "$has_ms" = 1 ] && \
[ "$issue_ok" = 1 ] && [ "${ncom:-0}" -ge 1 ] && [ "${nreact:-0}" -ge 1 ] && [ "$scratch_gone" = 1 ] && ok=1
echo $ok > /logs/verifier/reward.txt
echo "renamed=$renamed bug=$has_bug nodup=$no_dup ms=$has_ms issue=$issue_ok com=$ncom react=$nreact scratch_gone=$scratch_gone -> $ok"

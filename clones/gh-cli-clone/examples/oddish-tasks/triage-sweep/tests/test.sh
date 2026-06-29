#!/usr/bin/env bash
set -uo pipefail; mkdir -p /logs/verifier
R=acme/inbox
data=$(gh api "repos/$R/issues?type=issues&state=all&limit=50" 2>/dev/null)
py(){ echo "$data" | python3 -c "$1" 2>/dev/null || echo 0; }
bug_open=$(py 'import sys,json;xs=json.load(sys.stdin);print(sum(1 for i in xs if i["state"]=="open" and any(l["name"]=="bug" for l in i.get("labels",[]))))')
bug_ms=$(py 'import sys,json;xs=json.load(sys.stdin);print(int(all((i.get("milestone") or {}).get("title")=="v1.1" for i in xs if any(l["name"]=="bug" for l in i.get("labels",[])) and i["state"]=="open")))')
# the cosmetic issue must NOT be labeled bug
cosmetic_ok=$(py 'import sys,json;xs=json.load(sys.stdin);print(int(all(not any(l["name"]=="bug" for l in i.get("labels",[])) for i in xs if "copyright" in i["title"].lower())))')
# at least one closed issue with a comment (the duplicate)
closed_num=$(py 'import sys,json;xs=json.load(sys.stdin);cs=[i["number"] for i in xs if i["state"]=="closed"];print(cs[0] if cs else 0)')
ncom=0; [ "${closed_num:-0}" -ge 1 ] && ncom=$(gh api repos/$R/issues/$closed_num/comments 2>/dev/null | python3 -c 'import sys,json;print(len(json.load(sys.stdin)))' 2>/dev/null || echo 0)
ok=0
[ "${bug_open:-0}" = 2 ] && [ "${bug_ms:-0}" = 1 ] && [ "${cosmetic_ok:-0}" = 1 ] && [ "${ncom:-0}" -ge 1 ] && ok=1
echo $ok >/logs/verifier/reward.txt
echo "bug_open=$bug_open bug_ms=$bug_ms cosmetic_ok=$cosmetic_ok dup_comment=$ncom -> $ok"

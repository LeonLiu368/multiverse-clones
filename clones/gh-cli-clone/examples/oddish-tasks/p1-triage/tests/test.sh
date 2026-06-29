#!/usr/bin/env bash
set -uo pipefail; mkdir -p /logs/verifier
lbl=$(gh api "repos/acme/triage/labels" 2>/dev/null | python3 -c 'import sys,json;print(int(any(l.get("name")=="wontfix" for l in json.load(sys.stdin))))' 2>/dev/null || echo 0)
st=$(gh api "repos/acme/triage/issues/1" 2>/dev/null | python3 -c 'import sys,json;print(json.load(sys.stdin).get("state",""))' 2>/dev/null || echo "")
nc=$(gh api repos/acme/triage/issues/1/comments 2>/dev/null | python3 -c 'import sys,json;print(len(json.load(sys.stdin)))' 2>/dev/null || echo 0)
[ "${lbl:-0}" = "1" ] && [ "$st" = "closed" ] && [ "${nc:-0}" -ge 1 ] && echo 1 >/logs/verifier/reward.txt || echo 0 >/logs/verifier/reward.txt
echo "label=$lbl state=$st comments=$nc -> $(cat /logs/verifier/reward.txt)"

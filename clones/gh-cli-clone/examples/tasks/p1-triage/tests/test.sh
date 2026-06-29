#!/usr/bin/env bash
set -uo pipefail; mkdir -p /logs/verifier
has_label=$(gh label list -R ghc-admin/triage --json 2>/dev/null | python3 -c 'import sys,json;print(int(any(l.get("name")=="wontfix" for l in json.load(sys.stdin))))' 2>/dev/null || echo 0)
state=$(gh issue view 1 -R ghc-admin/triage --json 2>/dev/null | python3 -c 'import sys,json;print(json.load(sys.stdin).get("state",""))' 2>/dev/null || echo "")
ncomments=$(gh api repos/ghc-admin/triage/issues/1/comments 2>/dev/null | python3 -c 'import sys,json;print(len(json.load(sys.stdin)))' 2>/dev/null || echo 0)
if [ "${has_label:-0}" = "1" ] && [ "$state" = "closed" ] && [ "${ncomments:-0}" -ge 1 ]; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi
echo "label=$has_label state=$state comments=$ncomments -> $(cat /logs/verifier/reward.txt)"

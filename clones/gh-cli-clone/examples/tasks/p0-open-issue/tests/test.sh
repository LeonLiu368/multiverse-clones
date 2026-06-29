#!/usr/bin/env bash
set -uo pipefail; mkdir -p /logs/verifier
found=$(gh issue list -R ghc-admin/harbortask --state all --json 2>/dev/null | python3 -c 'import sys,json;print(sum(1 for i in json.load(sys.stdin) if i.get("title")=="GHCTASK-OK"))' 2>/dev/null || echo 0)
[ "${found:-0}" -ge 1 ] && echo 1 > /logs/verifier/reward.txt || echo 0 > /logs/verifier/reward.txt
cat /logs/verifier/reward.txt

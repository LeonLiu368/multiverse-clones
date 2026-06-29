#!/usr/bin/env bash
set -uo pipefail; mkdir -p /logs/verifier
ok=$(gh api "repos/acme/service/issues?type=issues&state=all&limit=50" 2>/dev/null | python3 -c 'import sys,json;print(int(any(i.get("title")=="DEPLOY-4F2A" for i in json.load(sys.stdin))))' 2>/dev/null || echo 0)
[ "$ok" = 1 ] && echo 1 >/logs/verifier/reward.txt || echo 0 >/logs/verifier/reward.txt
echo "deploy_code_issue=$ok -> $(cat /logs/verifier/reward.txt)"

#!/usr/bin/env bash
set -euo pipefail
R=acme/service
WF=$(gh workflow list -R $R | grep -oE '[^/ ]+\.ya?ml' | head -1)
gh workflow run "$WF" -R $R --ref main
for i in $(seq 1 60); do
  st=$(gh api repos/$R/actions/tasks 2>/dev/null | python3 -c 'import sys,json;ws=json.load(sys.stdin).get("workflow_runs",[]);print(ws[0]["status"] if ws else "none")' 2>/dev/null || echo none)
  [ "$st" = success ] && break
  [ "$st" = failure ] && { echo "build failed"; exit 1; }
  sleep 5
done
rm -rf /tmp/art && mkdir -p /tmp/art
gh run download -R $R -D /tmp/art
CODE=$(cat /tmp/art/*/deploy.txt | tr -d '[:space:]')
gh issue create -R $R -t "$CODE" -b "deploy code from the CI build artifact"

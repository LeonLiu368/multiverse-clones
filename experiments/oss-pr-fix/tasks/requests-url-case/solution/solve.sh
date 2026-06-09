#!/usr/bin/env bash
# Oracle: find the open case-sensitivity fix PR, approve and merge it.
set -euo pipefail

R=acme/webapp

PR_NUM=""
for _ in $(seq 1 15); do
  PR_NUM=$(gh pr list -R "$R" --state open --json number --jq '.[0].number' 2>/dev/null)
  [ -n "$PR_NUM" ] && break
  sleep 2
done
[ -z "$PR_NUM" ] && { echo "no open PR found on $R"; exit 1; }

gh pr review "$PR_NUM" -R "$R" --approve \
  -b "LGTM — adds .lower() before every scheme-sensitive startswith() call in adapters.py and sessions.py, correctly handling RFC 2396 case-insensitive schemes."

for i in $(seq 1 10); do
  gh pr merge "$PR_NUM" -R "$R" --method squash && break || sleep 3
done

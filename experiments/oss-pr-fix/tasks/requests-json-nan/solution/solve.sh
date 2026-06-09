#!/usr/bin/env bash
# Oracle: find the open JSON NaN fix PR, approve and merge it.
set -euo pipefail

R=acme/api-service

PR_NUM=""
for _ in $(seq 1 15); do
  PR_NUM=$(gh pr list -R "$R" --state open --json number --jq '.[0].number' 2>/dev/null)
  [ -n "$PR_NUM" ] && break
  sleep 2
done
[ -z "$PR_NUM" ] && { echo "no open PR found on $R"; exit 1; }

gh pr review "$PR_NUM" -R "$R" --approve \
  -b "LGTM — adds allow_nan=False to json.dumps and introduces InvalidJSONError so invalid float values fail loudly at the call site rather than producing a malformed request body."

for i in $(seq 1 10); do
  gh pr merge "$PR_NUM" -R "$R" --method squash && break || sleep 3
done

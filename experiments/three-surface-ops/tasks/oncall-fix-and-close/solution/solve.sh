#!/usr/bin/env bash
# Oracle: find the open fix PR, review it, approve, merge, close ticket.
set -euo pipefail

R=acme/webapp

PR_NUM=$(gh pr list -R "$R" --state open --json number --jq '.[0].number')
[ -z "$PR_NUM" ] && { echo "no open PR found on $R"; exit 1; }

gh pr review "$PR_NUM" -R "$R" --approve \
  -b "LGTM — adds the agreed \`if not term: return []\` guard before \`term[0]\` access."

for i in $(seq 1 10); do
  gh pr merge "$PR_NUM" -R "$R" --method squash && break || sleep 3
done

linear issue update PROD-101 --state Done 2>/dev/null \
  || linear issue close PROD-101 2>/dev/null \
  || true

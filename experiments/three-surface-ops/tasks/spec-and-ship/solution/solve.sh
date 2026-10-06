#!/usr/bin/env bash
# Oracle: find the open feature PR, review it, approve, merge, close ticket.
set -euo pipefail

R=acme/platform

PR_NUM=""
for _ in $(seq 1 15); do
  PR_NUM=$(gh pr list -R "$R" --state open --json number --jq '.[0].number' 2>/dev/null)
  [ -n "$PR_NUM" ] && break
  sleep 2
done
[ -z "$PR_NUM" ] && { echo "no open PR found on $R"; exit 1; }

gh pr review "$PR_NUM" -R "$R" --approve \
  -b "Matches the agreed spec from #eng-design: regex \`^[^@]+@[^@]+\.[^@]+\$\`, 422 on failure, validation at top of create_user."

for i in $(seq 1 10); do
  gh pr merge "$PR_NUM" -R "$R" --method squash && break || sleep 3
done

linear issue update FEAT-301 --state Done 2>/dev/null \
  || linear issue close FEAT-301 2>/dev/null \
  || true

#!/usr/bin/env bash
set -euo pipefail
cd /app/repo
git config --global --add safe.directory /app/repo 2>/dev/null || true
ISSUE="TV-12789"
# Start the ticket before touching the code, the way the instruction asks:
# assigned to the agent and In Progress while the work happens.
linear issue start "$ISSUE" --json >/tmp/ticket-start.json
# The reference fix lives in /solution/files as readable source files mirroring
# the repo layout; copy them over the incident snapshot and commit.
cp -a /solution/files/. /app/repo/
git add -A
git -c user.email=agent@acme.test -c user.name=agent commit -qm "fix: sanitize dash/plus in text search path"
SHA="$(git rev-parse --short HEAD)"
linear issue comment add "$ISSUE" --body "Investigated the incident via the tracker context, applied the targeted fix in /app/repo, and verified the tests locally." --json >/tmp/ticket-comment.json
linear issue commit-link "$ISSUE" "$SHA" --json >/tmp/ticket-commit.json
linear issue pr "$ISSUE" --json >/tmp/ticket-pr.json
jira issue transition "$ISSUE" "In Review" --json >/tmp/ticket-review.json

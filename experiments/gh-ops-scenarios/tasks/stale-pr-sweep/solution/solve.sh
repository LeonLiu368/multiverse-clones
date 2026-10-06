#!/usr/bin/env bash
# Oracle: close the two PRs whose linked issues are closed (#2, #3),
# leave the PR for open issue #1 untouched.
set -euo pipefail

R=acme/platform

# Get all open PRs as JSON
PRS=$(gh api "repos/$R/pulls?state=open" 2>/dev/null)

DARK_NUM=$(echo "$PRS" | python3 -c \
  'import sys,json; xs=json.load(sys.stdin); r=[p["number"] for p in xs if p["head"]["ref"]=="feat/dark-mode"]; print(r[0] if r else "")')

CSV_NUM=$(echo "$PRS" | python3 -c \
  'import sys,json; xs=json.load(sys.stdin); r=[p["number"] for p in xs if p["head"]["ref"]=="feat/export-csv"]; print(r[0] if r else "")')

if [ -n "$DARK_NUM" ]; then
  gh pr comment "$DARK_NUM" -R "$R" \
    -b "Closing: the linked issue #2 was resolved without this PR (design team deprioritized dark mode for v2.0)."
  gh pr close "$DARK_NUM" -R "$R"
fi

if [ -n "$CSV_NUM" ]; then
  gh pr comment "$CSV_NUM" -R "$R" \
    -b "Closing: the linked issue #3 was shipped via the Tableau integration instead."
  gh pr close "$CSV_NUM" -R "$R"
fi

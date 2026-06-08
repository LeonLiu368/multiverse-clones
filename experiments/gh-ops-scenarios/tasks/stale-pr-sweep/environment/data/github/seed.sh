#!/usr/bin/env bash
# Seed: acme/platform with 3 issues and 3 open PRs.
# Issues #1 stays open (active work). Issues #2 and #3 are closed (resolved
# without the corresponding PR). The agent must close PRs for #2 and #3 with
# comments, and leave the PR for #1 open.
set -uo pipefail

R=acme/platform

gh repo create "$R" -d "platform monorepo" >/dev/null 2>&1 || true

gh api "repos/$R/contents/README.md" -X POST \
  -f content="$(printf '# platform\nMonorepo for the acme platform v2.0.\n' | base64 -w0)" \
  -f message="initial: platform scaffold" \
  -f branch=main >/dev/null 2>&1 || true

# Get the main HEAD SHA for branch creation
SHA=$(gh api "repos/$R/git/refs/heads/main" --jq '.object.sha')

# Create feature branches
for branch in feat/auth-refresh feat/dark-mode feat/export-csv; do
  gh api "repos/$R/git/refs" -X POST \
    -f ref="refs/heads/$branch" -f sha="$SHA" >/dev/null 2>&1 || true
done

# Add a WIP commit to each branch so PRs have a real diff vs main
gh api "repos/$R/contents/src/auth/refresh.py" -X POST \
  -f content="$(printf '# auth refresh token rotation — WIP\n' | base64 -w0)" \
  -f message="wip: auth refresh token implementation" \
  -f branch=feat/auth-refresh >/dev/null 2>&1 || true

gh api "repos/$R/contents/src/ui/dark.css" -X POST \
  -f content="$(printf '/* dark mode variables — WIP */\n' | base64 -w0)" \
  -f message="wip: dark mode stylesheet" \
  -f branch=feat/dark-mode >/dev/null 2>&1 || true

gh api "repos/$R/contents/src/reports/export.py" -X POST \
  -f content="$(printf '# CSV export for reports — WIP\n' | base64 -w0)" \
  -f message="wip: CSV export for reports" \
  -f branch=feat/export-csv >/dev/null 2>&1 || true

# Create tracking issues (#1, #2, #3)
gh issue create -R "$R" \
  -t "Add auth refresh token support" \
  -b "Required for v2.0 session security. Active PR in progress." >/dev/null 2>&1 || true

gh issue create -R "$R" \
  -t "Dark mode for dashboard" \
  -b "Nice to have. Design team deprioritized this for v2.0." >/dev/null 2>&1 || true

gh issue create -R "$R" \
  -t "CSV export for analytics reports" \
  -b "Shipped via Tableau integration instead." >/dev/null 2>&1 || true

# Close issues #2 and #3 (their work was resolved another way)
gh issue close 2 -R "$R" >/dev/null 2>&1 || true
gh issue close 3 -R "$R" >/dev/null 2>&1 || true

# Open PRs (will be #4, #5, #6 in the shared issue+PR numbering space)
gh pr create -R "$R" \
  -t "feat: add auth refresh token support" \
  -H feat/auth-refresh -B main \
  -b "Implements refresh token rotation for v2.0 session security.

Resolves #1" >/dev/null 2>&1 || true

gh pr create -R "$R" \
  -t "feat: dark mode for dashboard" \
  -H feat/dark-mode -B main \
  -b "Adds dark mode toggle to the main dashboard.

Resolves #2" >/dev/null 2>&1 || true

gh pr create -R "$R" \
  -t "feat: CSV export for analytics reports" \
  -H feat/export-csv -B main \
  -b "Adds one-click CSV export to the reports page.

Resolves #3" >/dev/null 2>&1 || true

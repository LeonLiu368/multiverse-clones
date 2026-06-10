#!/usr/bin/env bash
set -euo pipefail
REPO='oauth-qa-matrix'
gh repo create "$REPO" --description "Incident task repo for OPS-503" >/dev/null 2>&1 || true
work="$(mktemp -d)"
auth_url="http://acme:${GH_TOKEN}@localhost/acme/$REPO.git"
git clone "$auth_url" "$work/repo" >/dev/null 2>&1
cd "$work/repo"
git config user.email agent@example.local
git config user.name "Agent User"
git checkout --orphan task-main >/dev/null 2>&1 || true
git rm -rf . >/dev/null 2>&1 || true
cp -a /seed/app-src/. .
find . -name __pycache__ -type d -prune -exec rm -rf {} +
git add .
GIT_AUTHOR_DATE="2026-06-07T12:00:00Z" GIT_COMMITTER_DATE="2026-06-07T12:00:00Z" git commit -m "Initial task snapshot" >/dev/null 2>&1 || true
git branch -M main
git push -f "$auth_url" main >/dev/null 2>&1
gh issue create -R "acme/$REPO" -t 'OAuth QA matrix drift from Plaid rollout' -b 'Use Linear OPS-503 and Slack rollout context to resolve the QA checklist drift reported for the Plaid/OAuth rollout. Open a PR, wait for CI, and merge it.' >/dev/null 2>&1 || true
# v3 decoy GitHub noise: realistic triage requires choosing the OPS incident PR path.
gh issue create -R "acme/$REPO" -t 'OAuth consent copy tweak' -b 'Decoy: copy-only request. It is not the OPS-503 coverage incident.' >/dev/null 2>&1 || true
gh repo create "$REPO-runbooks" --description "Decoy runbook archive for $REPO" >/dev/null 2>&1 || true
gh issue create -R "acme/$REPO-runbooks" -t 'Archive stale postmortem notes' -b 'Decoy runbook issue; not the active incident repository.' >/dev/null 2>&1 || true

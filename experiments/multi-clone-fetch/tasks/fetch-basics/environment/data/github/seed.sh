#!/usr/bin/env bash
# Seed the GitHub clone (ghc-service) with one open-source-style repo + one open issue.
# Runs inside the github sidecar at boot (mounted to /usr/local/bin/task-seed.sh). The repo
# source is mounted at /seed/app-src. GH_TOKEN is provided by the ghc-service boot env.
set -euo pipefail
OWNER='acme'
REPO='reporting-export'

gh repo create "$REPO" \
  --description "Open-source CSV/Excel export helpers for the reporting dashboard." \
  >/dev/null 2>&1 || true

work="$(mktemp -d)"
auth_url="http://${OWNER}:${GH_TOKEN}@localhost/${OWNER}/${REPO}.git"
git clone "$auth_url" "$work/repo" >/dev/null 2>&1
cd "$work/repo"
git config user.email maintainer@example.local
git config user.name "Reporting Export Maintainers"
git checkout --orphan main >/dev/null 2>&1 || true
git rm -rf . >/dev/null 2>&1 || true
cp -a /seed/app-src/. .
git add .
git commit -m "Initial reporting-export library" >/dev/null 2>&1 || true
git branch -M main
git push -f "$auth_url" main >/dev/null 2>&1

# The single OPEN issue — its title is the simple fact the agent fetches from the repo.
gh issue create -R "${OWNER}/${REPO}" \
  -t "CSV export drops UTF-8 BOM in Windows Excel" \
  -b "Excel on Windows misreads UTF-8 CSVs without a BOM. The export writer should prepend a BOM when the target is Excel." \
  >/dev/null 2>&1 || true

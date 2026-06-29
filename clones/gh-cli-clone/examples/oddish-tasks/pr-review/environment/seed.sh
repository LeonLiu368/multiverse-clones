#!/usr/bin/env bash
set -uo pipefail
R=acme/lib
gh repo create lib -d "library" >/dev/null 2>&1 || true
gh api repos/$R/branches -X POST -f new_branch_name=proposed -f old_branch_name=main >/dev/null 2>&1 || true
gh api repos/$R/contents/RISKY.txt -X POST -f content="$(printf 'untested risky change\n' | base64 -w0)" -f message="risky" -f branch=proposed >/dev/null 2>&1 || true
gh pr create -R $R -t "Proposed change (needs review)" -H proposed -B main -b "Please review before merge." >/dev/null 2>&1 || true

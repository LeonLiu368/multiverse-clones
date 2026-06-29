#!/usr/bin/env bash
set -euo pipefail
cd /tmp
gh repo clone ghc-admin/fixme
cd fixme
git checkout -b fix-div
printf 'def div(a, b):\n    return a / b if b else 0\n' > calc.py
git add -A
git commit -m "fix: div returns 0 on zero divisor"
git push origin fix-div
gh pr create -R ghc-admin/fixme -t "Fix divide by zero" -H fix-div -B main -b "closes #1"

#!/usr/bin/env bash
set -euo pipefail
cd /tmp && rm -rf fixme
gh repo clone acme/fixme
cd fixme
git checkout -b fix-div
printf 'def div(a, b):\n    return a / b if b else 0\n' > calc.py
git add -A && git commit -m "fix: guard zero divisor"
git push origin fix-div
gh pr create -R acme/fixme -t "Fix divide by zero" -H fix-div -B main -b "closes #1"

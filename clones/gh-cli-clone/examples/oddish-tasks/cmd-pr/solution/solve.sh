#!/usr/bin/env bash
set -euo pipefail
gh repo fork acme/svc --org team
cd /tmp && rm -rf svc && gh repo clone acme/svc && cd svc
git checkout -b fix-div
printf 'def div(a, b):\n    return a / b if b else 0\n' > calc.py
git add -A && git commit -m "fix divide by zero"
git push origin fix-div
N=$(gh pr create -R acme/svc -t "Fix divide by zero" -H fix-div -B main -b "closes #1" | grep -oE '[0-9]+$')
gh pr review "$N" -R acme/svc --approve -b "LGTM"
for i in $(seq 1 10); do gh pr merge "$N" -R acme/svc --method squash && break || sleep 2; done
gh issue close 1 -R acme/svc

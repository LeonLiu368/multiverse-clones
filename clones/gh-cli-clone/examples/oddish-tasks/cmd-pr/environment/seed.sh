#!/usr/bin/env bash
set -uo pipefail
gh api orgs -X POST -f username=team -f visibility=public >/dev/null 2>&1 || true
gh repo create svc -d "service" >/dev/null 2>&1 || true
gh api repos/acme/svc/contents/calc.py -X POST \
  -f content="$(printf 'def div(a, b):\n    return a / b\n' | base64 -w0)" \
  -f message="add calc" -f branch=main >/dev/null 2>&1 || true
gh issue create -R acme/svc -t "div crashes on zero" -b "fix calc.py" >/dev/null 2>&1 || true

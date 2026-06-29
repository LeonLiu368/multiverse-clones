#!/usr/bin/env bash
set -uo pipefail
gh repo create fixme -d "buggy" >/dev/null 2>&1 || true
gh api repos/acme/fixme/contents/calc.py -X POST \
  -f content="$(printf 'def div(a, b):\n    return a / b\n' | base64 -w0)" \
  -f message="add calc.py" -f branch=main >/dev/null 2>&1 || true
gh issue create -R acme/fixme -t "div crashes on zero" -b "calc.py div(a,b) raises on b==0" >/dev/null 2>&1 || true

#!/usr/bin/env bash
set -uo pipefail
gh repo create webapp -d "billing service" >/dev/null 2>&1 || true
gh api repos/acme/webapp/contents/billing.py -X POST \
  -f content="$(printf 'def split_bill(total, people):\n    return total / people\n' | base64 -w0)" \
  -f message="add billing" -f branch=main >/dev/null 2>&1 || true
gh issue create -R acme/webapp -t "Incident: /split 500s when people=0" \
  -b "ZeroDivisionError in billing.py split_bill when people==0. Expected 0.00. Fix and ship." >/dev/null 2>&1 || true

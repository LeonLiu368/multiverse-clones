#!/usr/bin/env bash
set -uo pipefail
gh repo create webapp -d "billing service" >/dev/null 2>&1 || true
gh api repos/acme/webapp/contents/billing.py -X POST \
  -f content="$(printf 'def split_bill(total, people):\n    """Split a bill evenly across people."""\n    return total / people\n' | base64 -w0)" \
  -f message="add billing" -f branch=main >/dev/null 2>&1 || true
gh api repos/acme/webapp/contents/README.md -X POST \
  -f content="$(printf '# webapp\nBilling service. `split_bill(total, people)` divides a bill.\n' | base64 -w0)" \
  -f message="readme" -f branch=main >/dev/null 2>&1 || true
gh issue create -R acme/webapp \
  -t "Incident: /split returns 500 when a table has 0 people" \
  -b "Production incident. Users hitting POST /split with people=0 get a 500. Logs show:

    ZeroDivisionError: division by zero
      File \"billing.py\", line 3, in split_bill
        return total / people

Expected: an empty table (0 people) should split to 0.00, not crash. Please fix and ship." >/dev/null 2>&1 || true

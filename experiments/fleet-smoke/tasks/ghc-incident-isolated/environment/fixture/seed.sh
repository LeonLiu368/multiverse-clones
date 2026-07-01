#!/usr/bin/env bash
# Per-task fixture seed (canon R2.d): MOUNTED into the gateway at /fixture and run
# by gateway-entrypoint.sh at first boot with GH_HOST/GH_TOKEN pointing at the
# local forge. Builds the incident world: acme/webapp + billing.py + the open
# split_bill incident issue. Never COPY'd into an image; never visible to `main`.
set -uo pipefail
gh repo create webapp -d "billing service" >/dev/null 2>&1 || true
# wait for the repo to materialize before writing contents (Forgejo is async)
for i in $(seq 1 20); do gh api repos/acme/webapp >/dev/null 2>&1 && break; sleep 0.5; done
gh api repos/acme/webapp/contents/billing.py -X POST \
  -f content="$(printf 'def split_bill(total, people):\n    return total / people\n' | base64 -w0)" \
  -f message="add billing" -f branch=main >/dev/null 2>&1 || true
gh issue create -R acme/webapp -t "Incident: /split 500s when people=0" \
  -b "ZeroDivisionError in billing.py split_bill when people==0. Expected 0.00. Fix and ship." >/dev/null 2>&1 || true

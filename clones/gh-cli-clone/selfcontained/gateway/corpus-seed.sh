#!/usr/bin/env bash
# Corpus seed for ghc-service:prod-v1 — the shared, realistic forge corpus that
# is BAKED INTO the image at build time (see Dockerfile.prod-v1). Runs once,
# against the local forge, as the admin user `acme`. Mirrors the historical
# per-task `seed.sh` so the bundled incident task still scores nop=0/oracle=1,
# but here it is image-build data, not per-task COPY.
#
# Invoked by gateway-entrypoint.sh in `--bake` mode with GH_HOST/GH_TOKEN set to
# the local forge.
set -uo pipefail

gh repo create webapp -d "billing service" >/dev/null 2>&1 || true
gh api repos/acme/webapp/contents/billing.py -X POST \
  -f content="$(printf 'def split_bill(total, people):\n    return total / people\n' | base64 -w0)" \
  -f message="add billing" -f branch=main >/dev/null 2>&1 || true
gh issue create -R acme/webapp -t "Incident: /split 500s when people=0" \
  -b "ZeroDivisionError in billing.py split_bill when people==0. Expected 0.00. Fix and ship." >/dev/null 2>&1 || true

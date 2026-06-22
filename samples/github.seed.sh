#!/usr/bin/env bash
# Per-task GitHub seed — a shell of `gh` API calls run at sidecar boot (ghc-service).
# The viewer parses these into a preview of the repos / issues / PRs / reviews they create.
set -euo pipefail

gh repo create acme/web --private --description "Payments + checkout web service"

gh issue create --repo acme/web \
  --title "Checkout 500s after deploy 2026-06-20" \
  --body "Spike in 500s on POST /checkout right after the Tuesday deploy. Looks payments-related." \
  --label bug --label incident --assignee robin.vega

gh issue create --repo acme/web \
  --title "Add idempotency key validation to refund endpoint" \
  --body "Reject malformed idempotency keys before refund creation." \
  --label backend

gh pr create --repo acme/web \
  --title "Fix checkout read timeout (5s -> 30s)" \
  --body "Bumps the payments client read timeout from 5s to 30s per the infra decision." \
  --head fix/read-timeout --base main

gh pr review 1 --repo acme/web --request-changes \
  --body "the read timeout must be 30s, not 5s — confirmed with infra. 5s trips on cold payments pods."

gh pr review 1 --repo acme/web --approve \
  --body "30s matches the infra runbook. LGTM once the regression test is added."

#!/usr/bin/env bash
# Vendor each clone's now-sourceless, pull-based task into ./tasks/<name>/ so the fleet smoke mirrors
# the canonical clone tasks. All 10 clone tasks pull their gateway + agent from ghcr.io/abundant-ai
# (no vendored source). Re-run to refresh after a clone task changes.
set -euo pipefail
cd "$(dirname "$0")"; ROOT=../../clones
map=$(cat <<'EOF'
notion-db-triage	notion-clone/oddish/tasks/notion-db-triage
figma-spec-recovery	figma-clone/oddish/tasks/figma-spec-recovery
gws-launch-date-prod-v1	google-workspace-clone/oddish/tasks/gws-launch-date-prod-v1
sentry-payments-incident	sentry-clone/tasks/payments-incident
grafana-annotation-roundtrip	grafana-clone/oddish/tasks/gauge-annotation-roundtrip
logfire-incident-rca	abundant-logfire-clone/oddish/tasks/logfire-incident-rca
aws-payment-reconcile	aws-clone/oddish/tasks/payment-reconcile
jira-transition-roundtrip	abundant-jira-clone/tasks/jira-transition-roundtrip
slack-incident-fix-report	abundant-slack-clone/oddish/tasks/incident-fix-report
EOF
)
printf '%s\n' "$map" | while IFS=$'\t' read -r name src; do
  [ -z "$name" ] && continue
  echo "vendoring $name <- clones/$src"
  rm -rf "tasks/$name"
  rsync -a --exclude='__pycache__' --exclude='*.pyc' --exclude='.venv' --exclude='.pytest_cache' "$ROOT/$src/" "tasks/$name/"
done
echo "done. tasks:"; ls tasks/

#!/usr/bin/env bash
# Vendor each fleet-smoke clone's self-contained Harbor/oddish task into ./tasks/<name>/ so the
# experiment is self-contained (mirrors the notion-smoke pattern). Re-run to refresh after a clone
# task changes. v1 covers the 7 clones whose tasks build standalone (no private base image, compose
# present, environment vendors its package + corpus).
set -euo pipefail
cd "$(dirname "$0")"
ROOT=../../clones
# name<TAB>clone/relpath-to-task
map=$(cat <<'EOF'
notion-db-triage	notion-clone/oddish/tasks/notion-db-triage
figma-spec-recovery	figma-clone/oddish/tasks/figma-spec-recovery
gws-launch-date-prod-v1	google-workspace-clone/oddish/tasks/gws-launch-date-prod-v1
sentry-payments-incident	sentry-clone/tasks/payments-incident
grafana-annotation-roundtrip	grafana-clone/oddish/tasks/gauge-annotation-roundtrip
logfire-incident-rca	abundant-logfire-clone/oddish/tasks/logfire-incident-rca
aws-payment-reconcile	aws-clone/oddish/tasks/payment-reconcile
EOF
)
printf '%s\n' "$map" | while IFS=$'\t' read -r name src; do
  [ -z "$name" ] && continue
  echo "vendoring $name <- clones/$src"
  rm -rf "tasks/$name"
  rsync -a --exclude='__pycache__' --exclude='*.pyc' --exclude='.venv' --exclude='.pytest_cache' \
    "$ROOT/$src/" "tasks/$name/"
done
echo "done. tasks:"; ls tasks/

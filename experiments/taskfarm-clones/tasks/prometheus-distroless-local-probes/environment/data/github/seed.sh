#!/usr/bin/env bash
set -euo pipefail
REPO='prometheus-distroless-local-probes'
gh repo create "$REPO" --description "Prometheus Operator listenLocal distroless probe incident" >/dev/null 2>&1 || true
work="$(mktemp -d)"
auth_url="http://acme:${GH_TOKEN}@localhost/acme/$REPO.git"
git clone "$auth_url" "$work/repo" >/dev/null 2>&1
cd "$work/repo"
git config user.email agent@example.local
git config user.name "Agent User"
git checkout --orphan main >/dev/null 2>&1 || true
git rm -rf . >/dev/null 2>&1 || true
cp -a /seed/app-src/. .
git add .
git commit -m "Initial Prometheus distroless listenLocal probe task repo" >/dev/null 2>&1 || true
git branch -M main
git push -f "$auth_url" main >/dev/null 2>&1
gh issue create -R "acme/$REPO" -t "PROMOP-8605 distroless listenLocal probes use shell exec" -b "Kubelet probe failures are scoped to prom-ceems-primary and prom-edge-rules. Avoid broad image rollback." >/dev/null 2>&1 || true
gh issue create -R "acme/$REPO" -t "PROMOP-8441 stale timeout branch" -b "Older timeout-only work; not authoritative for distroless shell failures." >/dev/null 2>&1 || true
gh issue create -R "acme/$REPO" -t "PROMOP-8612 public listener probe cleanup" -b "Related distroless image, but listenLocal is false." >/dev/null 2>&1 || true
git checkout -B probe-timeout-tuning >/dev/null 2>&1
mkdir -p notes
printf '%s\n' 'stale branch: increase failureThreshold only' 'not enough for PROMOP-8605 because sh is absent' > notes/probe-timeout.md
git add notes/probe-timeout.md
git commit -m "Record stale probe timeout tuning note" >/dev/null 2>&1 || true
git push -f "$auth_url" probe-timeout-tuning >/dev/null 2>&1 || true
git checkout main >/dev/null 2>&1

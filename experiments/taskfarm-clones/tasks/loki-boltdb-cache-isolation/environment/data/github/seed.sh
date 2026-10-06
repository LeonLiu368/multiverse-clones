#!/usr/bin/env bash
set -euo pipefail
REPO='loki-boltdb-cache-isolation'
gh repo create "$REPO" --description "Loki BoltDB shipper write replica path isolation incident" >/dev/null 2>&1 || true
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
git commit -m "Initial Loki BoltDB path isolation incident repo" >/dev/null 2>&1 || true
git branch -M main
git push -f "$auth_url" main >/dev/null 2>&1
gh issue create -R "acme/$REPO" -t "LOKI-3248 write replicas panic opening BoltDB index file" -b "Two write replicas share BoltDB shipper active/cache paths and crash on index_18652. Avoid deleting all Loki data; leave compactor paths alone." >/dev/null 2>&1 || true
gh issue create -R "acme/$REPO" -t "LOKI-3219 historical file size too small" -b "Closed reference from a previous damaged local BoltDB file. Do not use as scope for the current repair." >/dev/null 2>&1 || true
git checkout -B ops/cache-ttl-noise >/dev/null 2>&1
mkdir -p ops
printf '%s\n' 'handoff: stale cache ttl branch' 'not authoritative for LOKI-3248' > ops/cache-ttl-noise.txt
git add ops/cache-ttl-noise.txt
git commit -m "Add non-authoritative cache ttl notes" >/dev/null 2>&1 || true
git push -f "$auth_url" ops/cache-ttl-noise >/dev/null 2>&1 || true

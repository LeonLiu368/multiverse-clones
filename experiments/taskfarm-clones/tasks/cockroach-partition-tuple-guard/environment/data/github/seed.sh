#!/usr/bin/env bash
set -euo pipefail
REPO='cockroach-partition-tuple-guard'
gh repo create "$REPO" --description "CRDB-63642 partition tuple validation panic mirror" >/dev/null 2>&1 || true
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
git commit -m "Initial CRDB-63642 partition tuple guard mirror" >/dev/null 2>&1 || true
git branch -M main
git push -f "$auth_url" main >/dev/null 2>&1
gh issue create -R "acme/$REPO" -t "CRDB-63642 declarative schema change panic in partition tuple decode" -b "Sentry 7461557230 reports slice bounds out of range [2:0] under DecodePartitionTuple during ALTER PRIMARY KEY. Keep the repair scoped to the malformed CRDB-63642 rows." >/dev/null 2>&1 || true
gh issue create -R "acme/$REPO" -t "CRDB-63590 intentional empty partition list audit" -b "Nearby decoy: zero-arity empty partition list should remain valid." >/dev/null 2>&1 || true
gh issue create -R "acme/$REPO" -t "CRDB-63512 inventory hash shard validation" -b "Closed noise from the same descriptor validation area." >/dev/null 2>&1 || true
git checkout -B ops/crdb-63642-notes >/dev/null 2>&1
mkdir -p ops
printf '%s\n' 'ticket: CRDB-63642' 'avoid: skip all partition validation' 'artifact: /app/artifacts/cockroach_partition_tuple_guard_plan.json' > ops/handoff.txt
git add ops
git commit -m "Add CRDB-63642 ops handoff" >/dev/null 2>&1 || true
git push -f "$auth_url" ops/crdb-63642-notes >/dev/null 2>&1 || true
git checkout main >/dev/null 2>&1

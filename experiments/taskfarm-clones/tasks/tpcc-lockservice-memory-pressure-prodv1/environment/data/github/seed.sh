#!/usr/bin/env bash
set -euo pipefail
REPO='tpcc-lockservice-memory-pressure'
gh repo create "$REPO" --description "MatrixOne TPCC 1000W lockservice timeout under CN memory pressure" >/dev/null 2>&1 || true
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
git commit -m "Initial MatrixOne TPCC incident harness" >/dev/null 2>&1 || true
git branch -M main
git push -f "$auth_url" main >/dev/null 2>&1
gh issue create -R "acme/$REPO" -t "MO-24893 TPCC 1000W lockservice timeout under CN memory pressure" -b "Use local evidence, Postgres, and TicketVector to scope the repair. Smaller TPCC profiles passed; later IVF OOMKilled is unrelated." >/dev/null 2>&1 || true
gh issue create -R "acme/$REPO" -t "MO-24788 TPCC 100W retry audit" -b "Closed historical noise for smaller TPCC run; do not change while handling MO-24893." >/dev/null 2>&1 || true
git checkout -B ops-notes >/dev/null 2>&1
mkdir -p ops
printf '%s\n' 'MO-24893 handoff notes' 'wrong shortcut: disable TPCC or call the later IVF OOM the root cause' 'target backend: 10.143.26.143:6003' > ops/mo-24893-handoff.txt
git add ops >/dev/null 2>&1
git commit -m 'Add MO-24893 ops handoff notes' >/dev/null 2>&1 || true
git push -f "$auth_url" ops-notes >/dev/null 2>&1 || true

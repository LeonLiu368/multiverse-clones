#!/usr/bin/env bash
set -euo pipefail
REPO='cockroach-descriptor-backref-repair'
gh repo create "$REPO" --description "CockroachDB descriptor backref repair reproduction for CRDB-63963" >/dev/null 2>&1 || true
work="$(mktemp -d)"
auth_url="http://cockroach:${GH_TOKEN}@localhost/cockroach/$REPO.git"
git clone "$auth_url" "$work/repo" >/dev/null 2>&1
cd "$work/repo"
git config user.email agent@example.local
git config user.name "Agent User"
git checkout --orphan main >/dev/null 2>&1 || true
git rm -rf . >/dev/null 2>&1 || true
cp -a /seed/app-src/. .
git add .
git commit -m "Initial CRDB-63963 descriptor repair reproduction" >/dev/null 2>&1 || true
git branch -M main
git push -f "$auth_url" main >/dev/null 2>&1
gh issue create -R "cockroach/$REPO" -t "CRDB-63963 validate.go panic on missing depended-on-by descriptor" -b "Local reproduction of CockroachDB issue 170371. Inspect catalog_repair/planner.py, the Sentry event, and Postgres descriptor_backrefs before preparing the scoped repair." >/dev/null 2>&1 || true
gh issue create -R "cockroach/$REPO" -t "CRDB-63912 forward reference validation warning" -b "Background warning for descriptor_lease_table. This is not part of the depended-on-by repair." >/dev/null 2>&1 || true
git checkout -B sentry-170371-notes >/dev/null 2>&1
mkdir -p ops
cat > ops/descriptor-validation-notes.txt <<'EOF'
CRDB-63963 local incident notes

Primary Sentry event:
- evt-crdb-170371
- validate.go:358
- relation 193 -> referenced descriptor 400 missing
- stack key sql.schema.validation_errors.read.backward_references.relation

Additional affected local row:
- relation 211 -> referenced descriptor 417 missing

Noise:
- relation 244 references descriptor 612, which exists
- relation 305 is already dropped
- relation 318 is a forward-reference validation warning, not the read backward-reference panic
EOF
git add ops
git commit -m "Add descriptor validation incident notes" >/dev/null 2>&1 || true
git push -f "$auth_url" sentry-170371-notes >/dev/null 2>&1

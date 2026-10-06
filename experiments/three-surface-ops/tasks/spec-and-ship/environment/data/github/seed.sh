#!/usr/bin/env bash
# Seed: acme/platform with register.py missing email validation on main
#       AND a feature PR implementing it, open for review.
set -euo pipefail

REPO=platform
AUTH_REMOTE="http://acme:${GH_TOKEN}@localhost/acme/${REPO}.git"

gh repo create "$REPO" --description "acme platform service" >/dev/null 2>&1 || true

work="$(mktemp -d)"
git clone "$AUTH_REMOTE" "$work/repo" >/dev/null 2>&1
cd "$work/repo"
git config user.email seed@acme.internal
git config user.name "Alice"

# ── main: missing validation ──────────────────────────────────────────────────
git checkout --orphan task-main >/dev/null 2>&1 || true
git rm -rf . >/dev/null 2>&1 || true

cat > register.py << 'PYEOF'
import hashlib


def hash_password(pw):
    return hashlib.sha256(pw.encode()).hexdigest()


def create_user(email, password):
    """Register a new user. No email validation currently."""
    if not email or not password:
        return {"error": "email and password required"}, 400
    user = db.create({"email": email, "password": hash_password(password)})
    return {"id": user["id"], "email": user["email"]}, 201
PYEOF

cat > README.md << 'EOF'
# platform
The acme platform service.
EOF

git add .
GIT_AUTHOR_DATE="2026-06-01T12:00:00Z" GIT_COMMITTER_DATE="2026-06-01T12:00:00Z" \
  git commit -m "Initial snapshot" >/dev/null 2>&1
git push --force origin task-main:main >/dev/null 2>&1

# ── feature branch: email validation ─────────────────────────────────────────
git checkout -b feat/email-validation >/dev/null 2>&1

cat > register.py << 'PYEOF'
import hashlib
import re

_EMAIL_RE = re.compile(r'^[^@]+@[^@]+\.[^@]+$')


def hash_password(pw):
    return hashlib.sha256(pw.encode()).hexdigest()


def create_user(email, password):
    """Register a new user with email validation."""
    if not email or not password:
        return {"error": "email and password required"}, 400
    if not _EMAIL_RE.match(email):
        return {"error": "invalid email format"}, 422
    user = db.create({"email": email, "password": hash_password(password)})
    return {"id": user["id"], "email": user["email"]}, 201
PYEOF

GIT_AUTHOR_DATE="2026-06-03T14:00:00Z" GIT_COMMITTER_DATE="2026-06-03T14:00:00Z" \
  git commit -am "feat: add email validation to create_user (FEAT-301)" >/dev/null 2>&1
git push origin feat/email-validation >/dev/null 2>&1

# ── open PR ───────────────────────────────────────────────────────────────────
gh pr create -R "acme/$REPO" \
  --title "feat: add email validation to registration endpoint" \
  --head feat/email-validation --base main \
  --body "Adds server-side email validation to \`create_user\` in \`register.py\` per the spec agreed in \`#eng-design\`. Compiles \`^[^@]+@[^@]+\.[^@]+\$\` once at module level and checks it at the top of \`create_user\` before any DB call. Returns HTTP 422 with \`{\"error\": \"invalid email format\"}\` on failure. Closes FEAT-301." \
  >/dev/null 2>&1

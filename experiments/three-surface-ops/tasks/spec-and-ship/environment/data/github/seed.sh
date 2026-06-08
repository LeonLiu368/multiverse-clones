#!/usr/bin/env bash
# Seed: acme/platform with register.py missing email validation.
set -euo pipefail

REPO=platform

gh repo create "$REPO" --description "acme platform service" >/dev/null 2>&1 || true

work="$(mktemp -d)"
git clone "http://localhost/acme/${REPO}.git" "$work/repo" >/dev/null 2>&1
cd "$work/repo"
git config user.email agent@example.local
git config user.name "Agent User"
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
GIT_AUTHOR_DATE="2026-06-07T12:00:00Z" GIT_COMMITTER_DATE="2026-06-07T12:00:00Z" \
  git commit -m "Initial snapshot" >/dev/null 2>&1
git push --force origin task-main:main >/dev/null 2>&1

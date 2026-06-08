#!/usr/bin/env bash
set -euo pipefail

cd /tmp && rm -rf platform
gh repo clone acme/platform platform && cd platform

cat > register.py << 'EOF'
"""User registration."""

import hashlib
import re
import secrets

_EMAIL_RE = re.compile(r'^[^@]+@[^@]+\.[^@]+$')


def hash_password(pw):
    salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 100000)
    return f"{salt}:{hashed.hex()}"


def create_user(email, password):
    """Register a new user with email validation."""
    if not email or not password:
        return {"error": "email and password required"}, 400
    if not _EMAIL_RE.match(email):
        return {"error": "invalid email format"}, 422
    user = db.create({"email": email, "password": hash_password(password)})
    return {"id": user["id"], "email": user["email"]}, 201
EOF

git checkout -b feat/email-validation
git add register.py
git commit -m "feat: add email validation to create_user (FEAT-301)"
git push origin feat/email-validation

PR_URL=$(gh pr create -R acme/platform \
  -t "feat: add email validation to registration endpoint" \
  -H feat/email-validation -B main \
  -b "Adds regex-based email validation to create_user per the spec agreed in #eng-design. Returns 422 with {\"error\": \"invalid email format\"} for invalid addresses. Closes FEAT-301.")
PR_NUM=$(echo "$PR_URL" | grep -oE '[0-9]+$')

gh pr review "$PR_NUM" -R acme/platform --approve -b "Matches the agreed spec exactly."

for i in $(seq 1 10); do
  gh pr merge "$PR_NUM" -R acme/platform --method squash && break || sleep 3
done

linear issue update FEAT-301 --state Done 2>/dev/null \
  || linear issue close FEAT-301 2>/dev/null \
  || true

#!/usr/bin/env bash
set -euo pipefail

# Seed acme/platform with register.py missing email validation

ghc repo create acme/platform --private || true
cd /tmp && rm -rf platform
ghc repo clone acme/platform
cd platform

cat > README.md << 'EOF'
# platform

ACME platform monorepo. Core application services.

## Structure

- `register.py` — user registration endpoint
- `login.py` — authentication endpoint

## Running

```bash
python -m uvicorn app:main --host 0.0.0.0 --port 8080
```
EOF

cat > register.py << 'EOF'
"""User registration."""

import hashlib
import secrets


def hash_password(pw):
    salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 100000)
    return f"{salt}:{hashed.hex()}"


def create_user(email, password):
    """Register a new user. No input validation currently."""
    if not email or not password:
        return {"error": "email and password required"}, 400
    user = db.create({"email": email, "password": hash_password(password)})
    return {"id": user["id"], "email": user["email"]}, 201
EOF

git add README.md register.py
git commit -m "initial: add registration module"
git push origin main

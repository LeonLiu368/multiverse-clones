#!/usr/bin/env bash
# Seed: acme/webapp with a buggy search.py (crashes on empty term).
set -euo pipefail

REPO=webapp

gh repo create "$REPO" --description "acme web application" >/dev/null 2>&1 || true

work="$(mktemp -d)"
git clone "http://localhost/acme/${REPO}.git" "$work/repo" >/dev/null 2>&1
cd "$work/repo"
git config user.email agent@example.local
git config user.name "Agent User"
git checkout --orphan task-main >/dev/null 2>&1 || true
git rm -rf . >/dev/null 2>&1 || true

cat > search.py << 'PYEOF'
import re


_DB = {
    "users": [
        {"id": 1, "name": "alice"},
        {"id": 2, "name": "bob"},
        {"id": 3, "name": "carol"},
    ]
}


def search_users(term):
    """Search users whose name starts with the given prefix.

    Raises IndexError when term is empty.
    """
    prefix = term[0].lower()  # crashes if term == ""
    pattern = re.compile(rf"^{re.escape(prefix)}", re.IGNORECASE)
    return [u for u in _DB["users"] if pattern.match(u["name"])]


def get_user(user_id):
    users = [u for u in _DB["users"] if u["id"] == user_id]
    return users[0] if users else None
PYEOF

cat > README.md << 'EOF'
# webapp
The acme web application.
EOF

git add .
GIT_AUTHOR_DATE="2026-06-07T12:00:00Z" GIT_COMMITTER_DATE="2026-06-07T12:00:00Z" \
  git commit -m "Initial snapshot" >/dev/null 2>&1
git push origin task-main:main >/dev/null 2>&1

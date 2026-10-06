#!/usr/bin/env bash
# Seed: acme/webapp with buggy search.py on main AND a fix PR open for review.
set -euo pipefail

REPO=webapp
AUTH_REMOTE="http://acme:${GH_TOKEN}@localhost/acme/${REPO}.git"

gh repo create "$REPO" --description "acme web application" >/dev/null 2>&1 || true

work="$(mktemp -d)"
git clone "$AUTH_REMOTE" "$work/repo" >/dev/null 2>&1
cd "$work/repo"
git config user.email seed@acme.internal
git config user.name "Bob"

# ── main: buggy code ──────────────────────────────────────────────────────────
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
git push --force origin task-main:main >/dev/null 2>&1

# ── fix branch: correct code ─────────────────────────────────────────────────
git checkout -b fix/search-empty-term >/dev/null 2>&1

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
    """Search users whose name starts with the given prefix."""
    if not term:
        return []
    prefix = term[0].lower()
    pattern = re.compile(rf"^{re.escape(prefix)}", re.IGNORECASE)
    return [u for u in _DB["users"] if pattern.match(u["name"])]


def get_user(user_id):
    users = [u for u in _DB["users"] if u["id"] == user_id]
    return users[0] if users else None
PYEOF

GIT_AUTHOR_DATE="2026-06-08T09:35:00Z" GIT_COMMITTER_DATE="2026-06-08T09:35:00Z" \
  git commit -am "fix: guard against empty term in search_users (PROD-101)" >/dev/null 2>&1
git push origin fix/search-empty-term >/dev/null 2>&1

# ── open PR ───────────────────────────────────────────────────────────────────
gh pr create -R "acme/$REPO" \
  --title "fix: handle empty search term in search_users" \
  --head fix/search-empty-term --base main \
  --body "Adds \`if not term: return []\` guard at the top of \`search_users\` before the \`term[0]\` access. Prevents \`IndexError: string index out of range\` when the HTTP request sends \`?q=\` with an empty value. Closes PROD-101." \
  >/dev/null 2>&1

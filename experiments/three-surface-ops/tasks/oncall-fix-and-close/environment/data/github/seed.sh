#!/usr/bin/env bash
# Seed: acme/webapp with a buggy search.py (crashes on empty term).
# Runs inside the github sidecar with GH_HOST=http://localhost and GH_TOKEN set.
set -uo pipefail

R=acme/webapp

gh repo create "$R" -d "acme web application" >/dev/null 2>&1 || true

# Seed the buggy search module
SEARCH=$(cat <<'PYEOF' | base64 -w0
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
)

gh api "repos/$R/contents/search.py" -X POST \
  -f content="$SEARCH" \
  -f message="add search module" \
  -f branch=main >/dev/null 2>&1 || true

gh api "repos/$R/contents/README.md" -X POST \
  -f content="$(printf '# webapp\nThe acme web application.\n' | base64 -w0)" \
  -f message="readme" \
  -f branch=main >/dev/null 2>&1 || true

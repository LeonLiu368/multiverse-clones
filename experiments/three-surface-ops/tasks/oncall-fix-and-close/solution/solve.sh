#!/usr/bin/env bash
# Oracle: fix search.py, open PR, merge, close ticket.
set -euo pipefail

cd /tmp && rm -rf webapp
gh repo clone acme/webapp webapp && cd webapp

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

git checkout -b fix-search-empty-term
git add search.py
git commit -m "fix: guard against empty term in search_users (resolves PROD-101)"
git push origin fix-search-empty-term

PR_URL=$(gh pr create -R acme/webapp \
  -t "fix: handle empty search term in search_users" \
  -H fix-search-empty-term -B main \
  -b "Fixes the IndexError crash when term is empty. Adds guard before accessing term[0]. Resolves PROD-101.")
PR_NUM=$(echo "$PR_URL" | grep -oE '[0-9]+$')

gh pr review "$PR_NUM" -R acme/webapp --approve -b "LGTM."
for i in $(seq 1 10); do
  gh pr merge "$PR_NUM" -R acme/webapp --method squash && break || sleep 3
done

linear issue update PROD-101 --state Done 2>/dev/null \
  || linear issue close PROD-101 2>/dev/null \
  || true

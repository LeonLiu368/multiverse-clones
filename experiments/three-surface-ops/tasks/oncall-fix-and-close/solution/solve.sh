#!/usr/bin/env bash
# Oracle: read incident (PROD-101) and Slack, fix search.py, PR, merge, close ticket.
set -euo pipefail

# 1. Fix search.py — add empty-term guard
cd /tmp && rm -rf webapp
gh repo clone acme/webapp && cd webapp

cat > search.py <<'EOF'
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

    Returns empty list for empty search term.
    """
    if not term:
        return []
    prefix = term[0].lower()
    pattern = re.compile(rf"^{re.escape(prefix)}", re.IGNORECASE)
    return [u for u in _DB["users"] if pattern.match(u["name"])]


def get_user(user_id):
    users = [u for u in _DB["users"] if u["id"] == user_id]
    return users[0] if users else None
EOF

git checkout -b fix-search-empty-term
git add search.py
git commit -m "fix: guard against empty term in search_users (resolves PROD-101)"
git push origin fix-search-empty-term

# 2. Open PR, approve, merge
PR_URL=$(gh pr create -R acme/webapp \
  -t "fix: handle empty search term in search_users" \
  -H fix-search-empty-term -B main \
  -b "Fixes the IndexError crash when term is empty. Adds \`if not term: return []\` guard before accessing term[0]. Resolves PROD-101.")
PR_NUM=$(echo "$PR_URL" | grep -oE '[0-9]+$')

gh pr review "$PR_NUM" -R acme/webapp --approve -b "LGTM — guard is correct, matches the fix agreed in #ops-oncall."

for i in $(seq 1 10); do
  gh pr merge "$PR_NUM" -R acme/webapp --method squash && break || sleep 3
done

# 3. Update ticket to Done via linear CLI
linear issue edit PROD-101 --state Done 2>/dev/null \
  || linear issue close PROD-101 2>/dev/null \
  || true

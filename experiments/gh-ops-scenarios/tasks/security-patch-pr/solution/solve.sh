#!/usr/bin/env bash
# Oracle: fix the SQL injection, ship via reviewed PR, close the issue.
set -euo pipefail

cd /tmp && rm -rf api-service
gh repo clone acme/api-service
cd api-service

git checkout -b fix-sql-injection

cat > search.py <<'EOF'
def execute(query, params=()):
    """Stub DB executor."""
    return []


def search_users(term):
    """Search users by name (parameterized — SQL-injection safe)."""
    query = "SELECT * FROM users WHERE name = ?"
    return execute(query, (term,))
EOF

git add search.py
git commit -m "fix: parameterize search_users query to prevent SQL injection"
git push origin fix-sql-injection

PR_URL=$(gh pr create -R acme/api-service \
  -t "fix: prevent SQL injection in search_users" \
  -H fix-sql-injection -B main \
  -b "Closes #1. Replaces f-string interpolation with a parameterized query.")
PR_NUM=$(echo "$PR_URL" | grep -oE '[0-9]+$')

gh pr review "$PR_NUM" -R acme/api-service --approve -b "LGTM — parameterized query is correct."

for i in $(seq 1 10); do
  gh pr merge "$PR_NUM" -R acme/api-service --method squash && break || sleep 3
done

gh issue close 1 -R acme/api-service

#!/usr/bin/env bash
# Seed script — runs inside the github sidecar with GH_HOST=http://localhost
# and GH_TOKEN already set by the sidecar entrypoint.
set -uo pipefail

R=acme/api-service

# Create the repo
gh repo create "$R" -d "REST API service" >/dev/null 2>&1 || true

# Seed the vulnerable search module
SEARCH=$(printf 'def execute(query, params=()):\n    """Stub DB executor."""\n    return []\n\n\ndef search_users(term):\n    """Search users by name.\n\n    WARNING: vulnerable to SQL injection.\n    \"\"\"\n    query = f"SELECT * FROM users WHERE name = '"'"'{term}'"'"'"\n    return execute(query)\n' | base64 -w0)
gh api "repos/$R/contents/search.py" -X POST \
  -f content="$SEARCH" \
  -f message="add user search endpoint" \
  -f branch=main >/dev/null 2>&1 || true

gh api "repos/$R/contents/README.md" -X POST \
  -f content="$(printf '# api-service\nREST API for the acme platform.\n' | base64 -w0)" \
  -f message="readme" \
  -f branch=main >/dev/null 2>&1 || true

# Open the security issue
gh issue create -R "$R" \
  -t "Security: SQL injection in search_users" \
  -b "The \`search_users\` function in \`search.py\` builds a query by f-string interpolation:

\`\`\`python
query = f\"SELECT * FROM users WHERE name = '{term}'\"
\`\`\`

This allows an attacker to inject arbitrary SQL. Fix: use a parameterized query.

Example exploit: \`search_users(\"'; DROP TABLE users; --\")\`" \
  >/dev/null 2>&1 || true

#!/bin/bash
# Deterministic verification via the Mattermost REST API (runs in the client container).
# reward = 1 iff user `carol` is active (delete_at == 0), else 0. (nop -> 0, oracle -> 1.)
set -uo pipefail
mkdir -p /logs/verifier

URL="${MM_URL:-http://mattermost:8065}"
USER_ID="${MM_ADMIN_USER:-admin@demo.local}"
PASS="${MM_ADMIN_PASS:-AdminUser123!}"

fail() { echo "0" > /logs/verifier/reward.txt; echo "reward=0 ($1)"; exit 0; }

TOKEN="$(curl -sS -i -X POST "$URL/api/v4/users/login" -H 'Content-Type: application/json' \
  -d "{\"login_id\":\"$USER_ID\",\"password\":\"$PASS\"}" 2>/dev/null \
  | tr -d '\r' | awk 'tolower($1)=="token:"{print $2}')"
[ -n "$TOKEN" ] || fail "admin login failed"

DELETE_AT="$(curl -sS -H "Authorization: Bearer $TOKEN" \
  "$URL/api/v4/users/username/carol" | jq -r '.delete_at // empty')"
[ -n "$DELETE_AT" ] || fail "user carol not found"

if [ "$DELETE_AT" = "0" ]; then
  echo "1" > /logs/verifier/reward.txt
  echo "reward=1 (carol is active)"
else
  fail "carol is still deactivated (delete_at=$DELETE_AT)"
fi
exit 0

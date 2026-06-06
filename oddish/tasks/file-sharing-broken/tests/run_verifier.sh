#!/bin/bash
# Deterministic verification via the Mattermost REST API (runs in the client container).
# reward = 1 iff FileSettings.EnableFileAttachments is true in the server config, else 0.
# (nop -> 0, oracle -> 1.)
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

VAL="$(curl -sS -H "Authorization: Bearer $TOKEN" "$URL/api/v4/config" \
  | jq -r '.FileSettings.EnableFileAttachments')"

if [ "$VAL" = "true" ]; then
  echo "1" > /logs/verifier/reward.txt
  echo "reward=1 (file attachments enabled)"
else
  fail "file attachments still disabled (EnableFileAttachments=$VAL)"
fi
exit 0

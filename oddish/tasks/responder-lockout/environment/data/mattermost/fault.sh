#!/usr/bin/env bash
# FAULT (responder-lockout): deactivate the user `carol`, so she is locked out of the
# workspace. Runs inside the Mattermost container at seed time (server is on localhost).
set -uo pipefail
URL="http://localhost:8065"

TOK="$(curl -s -i -X POST "$URL/api/v4/users/login" -H 'Content-Type: application/json' \
  -d '{"login_id":"admin@demo.local","password":"AdminUser123!"}' \
  | tr -d '\r' | awk 'tolower($1)=="token:"{print $2}')"

USER_ID="$(curl -s -H "Authorization: Bearer $TOK" "$URL/api/v4/users/username/carol" | jq -r '.id')"
curl -s -X PUT -H "Authorization: Bearer $TOK" -H 'Content-Type: application/json' \
  -d '{"active":false}' "$URL/api/v4/users/$USER_ID/active" >/dev/null

echo "fault(responder-lockout): deactivated carol ($USER_ID)"

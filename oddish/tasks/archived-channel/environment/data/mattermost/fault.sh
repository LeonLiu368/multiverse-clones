#!/usr/bin/env bash
# FAULT (archived-channel): archive the #deploys channel so it disappears from the
# workspace. Runs inside the Mattermost container at seed time (server on localhost).
set -uo pipefail
URL="http://localhost:8065"

TOK="$(curl -s -i -X POST "$URL/api/v4/users/login" -H 'Content-Type: application/json' \
  -d '{"login_id":"admin@demo.local","password":"AdminUser123!"}' \
  | tr -d '\r' | awk 'tolower($1)=="token:"{print $2}')"
TID="$(curl -s -H "Authorization: Bearer $TOK" "$URL/api/v4/teams/name/test-demo" | jq -r '.id')"
CID="$(curl -s -H "Authorization: Bearer $TOK" "$URL/api/v4/teams/$TID/channels/name/deploys" | jq -r '.id')"

curl -s -X DELETE -H "Authorization: Bearer $TOK" "$URL/api/v4/channels/$CID" >/dev/null
echo "fault(archived-channel): archived #deploys ($CID)"

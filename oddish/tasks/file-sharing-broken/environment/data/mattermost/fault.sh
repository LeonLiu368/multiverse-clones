#!/usr/bin/env bash
# FAULT (file-sharing-broken): disable file attachments server-wide, so nobody can upload
# or share files in any channel. Runs inside the Mattermost container at seed time.
# Uses a get-modify-put on the server config (the same thing `mmctl config set` does).
set -uo pipefail
URL="http://localhost:8065"

TOK="$(curl -s -i -X POST "$URL/api/v4/users/login" -H 'Content-Type: application/json' \
  -d '{"login_id":"admin@demo.local","password":"AdminUser123!"}' \
  | tr -d '\r' | awk 'tolower($1)=="token:"{print $2}')"

CFG="$(curl -s -H "Authorization: Bearer $TOK" "$URL/api/v4/config")"
NEW="$(echo "$CFG" | jq '.FileSettings.EnableFileAttachments=false')"
curl -s -X PUT -H "Authorization: Bearer $TOK" -H 'Content-Type: application/json' \
  -d "$NEW" "$URL/api/v4/config" >/dev/null

echo "fault(file-sharing-broken): disabled FileSettings.EnableFileAttachments"

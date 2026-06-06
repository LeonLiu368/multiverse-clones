#!/bin/bash
# Deterministic verification via the Mattermost REST API (runs in the client container).
# reward = 1 iff the #deploys channel exists and is NOT archived (delete_at == 0), else 0.
# An archived channel drops out of the channel-by-name lookup, so "restored" == it resolves
# with delete_at 0. (nop -> 0, oracle -> 1.)
set -uo pipefail
mkdir -p /logs/verifier

URL="${MM_URL:-http://mattermost:8065}"
TEAM="${MM_TEAM:-test-demo}"
USER_ID="${MM_ADMIN_USER:-admin@demo.local}"
PASS="${MM_ADMIN_PASS:-AdminUser123!}"

fail() { echo "0" > /logs/verifier/reward.txt; echo "reward=0 ($1)"; exit 0; }

TOKEN="$(curl -sS -i -X POST "$URL/api/v4/users/login" -H 'Content-Type: application/json' \
  -d "{\"login_id\":\"$USER_ID\",\"password\":\"$PASS\"}" 2>/dev/null \
  | tr -d '\r' | awk 'tolower($1)=="token:"{print $2}')"
[ -n "$TOKEN" ] || fail "admin login failed"

TEAM_ID="$(curl -sS -H "Authorization: Bearer $TOKEN" "$URL/api/v4/teams/name/$TEAM" | jq -r '.id // empty')"
[ -n "$TEAM_ID" ] || fail "team $TEAM not found"

DELETE_AT="$(curl -sS -H "Authorization: Bearer $TOKEN" \
  "$URL/api/v4/teams/$TEAM_ID/channels/name/deploys" | jq -r '.delete_at // empty')"

if [ "$DELETE_AT" = "0" ]; then
  echo "1" > /logs/verifier/reward.txt
  echo "reward=1 (#deploys is active/restored)"
else
  fail "#deploys is missing or archived (delete_at=${DELETE_AT:-none})"
fi
exit 0

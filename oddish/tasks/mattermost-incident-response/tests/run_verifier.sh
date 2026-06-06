#!/bin/bash
# Deterministic verification via the Mattermost REST API. reward = 1 iff ALL of:
#   (a) a post in #incidents contains "root cause" AND "connection pool"
#   (b) a channel named `inc-checkout-latency` exists on team test-demo
#   (c) a post in that channel contains "summary" AND "connection pool"
# else reward = 0. (nop -> 0, oracle -> 1.) Runs in the client container (curl + jq).
set -uo pipefail
mkdir -p /logs/verifier

URL="${MM_URL:-http://mattermost:8065}"
TEAM="${MM_TEAM:-test-demo}"
USER_ID="${MM_ADMIN_USER:-admin@demo.local}"
PASS="${MM_ADMIN_PASS:-AdminUser123!}"

fail() { echo "0" > /logs/verifier/reward.txt; echo "reward=0 ($1)"; exit 0; }

# Admin login -> session token (returned in the `Token` response header).
TOKEN="$(curl -sS -i -X POST "$URL/api/v4/users/login" \
  -H 'Content-Type: application/json' \
  -d "{\"login_id\":\"$USER_ID\",\"password\":\"$PASS\"}" 2>/dev/null \
  | tr -d '\r' | awk 'tolower($1)=="token:"{print $2}')"
[ -n "$TOKEN" ] || fail "admin login failed"
AUTH=(-H "Authorization: Bearer $TOKEN")

TEAM_ID="$(curl -sS "${AUTH[@]}" "$URL/api/v4/teams/name/$TEAM" | jq -r '.id // empty')"
[ -n "$TEAM_ID" ] || fail "team $TEAM not found"

channel_id() { curl -sS "${AUTH[@]}" "$URL/api/v4/teams/$TEAM_ID/channels/name/$1" | jq -r '.id // empty'; }

# Count posts in channel $1 whose message contains both keywords $2 and $3 (case-insensitive).
count_posts_with() {
  curl -sS "${AUTH[@]}" "$URL/api/v4/channels/$1/posts?per_page=200" \
    | jq --arg a "$2" --arg b "$3" \
      '[.posts[]? | select((.message|ascii_downcase|contains($a)) and (.message|ascii_downcase|contains($b)))] | length' 2>/dev/null
}

# (a) ROOT CAUSE posted in #incidents
INC_ID="$(channel_id incidents)"
[ -n "$INC_ID" ] || fail "#incidents not found"
A="$(count_posts_with "$INC_ID" "root cause" "connection pool")"
[ "${A:-0}" -ge 1 ] || fail "no ROOT CAUSE naming the connection pool in #incidents"

# (b) dedicated incident channel created
NEW_ID="$(channel_id inc-checkout-latency)"
[ -n "$NEW_ID" ] || fail "channel inc-checkout-latency was not created"

# (c) SUMMARY posted in the new channel
C="$(count_posts_with "$NEW_ID" "summary" "connection pool")"
[ "${C:-0}" -ge 1 ] || fail "no SUMMARY naming the connection pool in #inc-checkout-latency"

echo "1" > /logs/verifier/reward.txt
echo "reward=1 (root-cause posted + incident channel created + summary posted)"
exit 0

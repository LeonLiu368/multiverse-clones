#!/usr/bin/env bash
# Configure the agent's "Slack" so curl + slack_sdk just work, then stay alive. The backend is
# addressed by IP (resolved at runtime) so the agent never sees a service name, port, or
# /api/v4 — only http://<ip>/api/<method>, like a self-hosted Slack-compatible endpoint.
set -uo pipefail
TOK=/run/secrets/slack_token

# Wait for the backend to deliver the token (= seeding finished).
for i in $(seq 1 180); do [ -s "$TOK" ] && break; sleep 1; done

# Resolve the backend IP so no service name appears in any URL the agent uses.
IP="$(getent hosts api 2>/dev/null | awk '{print $1; exit}')"
IP="${IP:-api}"
BASE="http://${IP}"
TOKEN="$(cat "$TOK" 2>/dev/null || true)"

# Make it ambient for the agent's shell + python sessions.
printf 'export SLACK_API_URL=%s\nexport SLACK_BOT_TOKEN=%s\n' "$BASE" "$TOKEN" > /etc/profile.d/slack.sh
printf 'SLACK_API_URL=%s\nSLACK_BOT_TOKEN=%s\n' "$BASE" "$TOKEN" > /root/.slack_env
export SLACK_API_URL="$BASE" SLACK_BOT_TOKEN="$TOKEN"

echo "[main] Slack API at ${BASE} (token ${TOKEN:0:9}…); slack_sdk + curl ready."
exec tail -f /dev/null

#!/usr/bin/env bash
# Keep the agent container alive. Slack creds are baked as env (SLACK_API_URL / SLACK_BOT_TOKEN),
# and the agent only starts once the backend is healthy (depends_on), i.e. after seeding — so
# curl + slack_sdk work immediately with no setup.
set -uo pipefail
exec tail -f /dev/null

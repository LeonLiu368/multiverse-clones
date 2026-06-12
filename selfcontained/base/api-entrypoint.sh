#!/usr/bin/env bash
# Entrypoint for the slack-service image run directly (gateway as the container's main process).
# Imports the seed into SQLite and runs the Slack Web API gateway on :80. No Mattermost/Postgres.
set -uo pipefail
source /usr/local/bin/slack-boot.sh
# Keep the gateway (started in the background by slack-boot.sh) in the foreground.
wait "${GW_PID:-}"

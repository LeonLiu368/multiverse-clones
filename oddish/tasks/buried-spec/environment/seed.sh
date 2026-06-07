#!/usr/bin/env bash
# Per-task seed hook (canonical artifact: no-op). The chat workspace is seeded from
# /data/mattermost/scraped.json by seed.py before this runs. Override this file in a task to do
# extra setup. If it needs to call the Slack API, note the gateway isn't up yet here — use
# Mattermost REST on http://localhost:8065 with an admin login, or just rely on scraped.json.
set -uo pipefail
exit 0

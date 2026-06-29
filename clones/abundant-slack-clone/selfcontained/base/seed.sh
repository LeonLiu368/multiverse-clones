#!/usr/bin/env bash
# Per-task seed hook (canonical artifact: no-op). The workspace is seeded from the real Slack export
# at /data/slack-export by import_export.py before this runs. slack-boot.sh runs this hook AFTER the
# gateway is up, so it may call the Slack API at http://localhost (e.g. to post extra planted
# messages). Override this file in a task for extra setup; most tasks need nothing here.
set -uo pipefail
exit 0

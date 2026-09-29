#!/usr/bin/env bash
# Oracle that genuinely chains the two hops via gws-cli (proves the tool path):
#   hop 1 (Gmail): find the launch thread, read its FINAL message -> authoritative
#                  event name 'Atlas Launch — GA'
#   hop 2 (Calendar): resolve that event -> its start date (2026-10-06)
set -euo pipefail

# hop 1: confirm the authoritative event name appears in the launch email thread
TID=$(gws-cli gmail search "Atlas launch" --format markdown | head -1 | awk '{print $2}' | sed 's/thread=//')
gws-cli gmail thread "$TID" --text | grep -q "Atlas Launch — GA" || { echo "oracle: authoritative event not found in email"; exit 1; }

# hop 2: resolve that event's start date from the calendar
EVID=$(gws-cli calendar events -q "Atlas Launch — GA" --format markdown | head -1 | awk '{print $1}')
DATE=$(gws-cli calendar get "$EVID" \
  | python3 -c "import sys,json; s=json.load(sys.stdin)['start']; print((s.get('dateTime') or s.get('date'))[:10])")

[ -n "$DATE" ] || { echo "oracle: failed to resolve date"; exit 1; }
cat > /app/launch/plan.py <<PY
"""The Atlas launch date (GA event named as authoritative in the launch email thread)."""
from __future__ import annotations


def launch_date() -> str:
    return "$DATE"
PY
echo "oracle: chained Gmail->Calendar, wrote $DATE"

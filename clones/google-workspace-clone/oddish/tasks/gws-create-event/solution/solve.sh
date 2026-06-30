#!/usr/bin/env bash
# Oracle: read the scheduling thread (disambiguating the superseded DRAFT), then
# CREATE the confirmed event via gws-cli (a real write through the calendar API).
#   thread says: 'Q3 Retro', 2026-10-06, 14:00-15:00 UTC (Priya's confirmation;
#   the draft-bot's Oct 3 10:00 is a decoy to be ignored).
set -euo pipefail

# hop 1 (Gmail): find + read the scheduling thread, confirm the authoritative ask
TID=$(gws-cli gmail search "Scheduling" --format markdown | head -1 | awk '{print $2}' | sed 's/thread=//')
gws-cli gmail thread "$TID" --text | grep -q "Q3 Retro" || { echo "oracle: confirmed ask not found"; exit 1; }

# hop 2 (Calendar WRITE): create the confirmed event
gws-cli calendar create \
  -s "Q3 Retro" \
  --start "2026-10-06T14:00:00Z" \
  --end "2026-10-06T15:00:00Z"

echo "oracle: created 'Q3 Retro' on 2026-10-06 via calendar write"

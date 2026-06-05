#!/bin/bash
# Oracle: post a concise decision summary to #design-decisions, then pin it.
set -euo pipefail
resp="$(slack-cli post design-decisions "DECISION: adopt react-aria for the booking-flow date picker — accessible (WCAG) unstyled primitives, no heavy deps; rejected react-datepicker (weak a11y, pulls in moment.js) and a custom build (too much maintenance).")"
ts="$(printf '%s' "$resp" | jq -r '.ts')"
slack-cli pin design-decisions "$ts"
echo "oracle posted and pinned decision (ts=$ts) to #design-decisions"

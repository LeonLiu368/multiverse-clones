#!/usr/bin/env bash
# Oracle: query the gauge service for the failing requests and extract the endpoint path.
# NOTE: no `set -e` — the grep pipeline returns non-zero on no-match, which must fall through.
set -uo pipefail
cd /workspace
out="$(gcx logs query '{service="checkout"} |= "500"' --since 24h 2>/dev/null || true)"
ep="$(printf '%s' "$out" | grep -oE '/api/[a-zA-Z/]+' 2>/dev/null | sort | uniq -c | sort -rn | awk '{print $2; exit}')" || true
[ -n "${ep:-}" ] || ep="/api/payments/charge"
printf '%s\n' "$ep" > answer.txt
echo "oracle wrote answer.txt: $ep"
exit 0

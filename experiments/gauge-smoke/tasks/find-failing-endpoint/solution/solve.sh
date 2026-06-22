#!/usr/bin/env bash
# Oracle: query the gauge service for the failing requests and extract the endpoint path.
set -euo pipefail
cd /workspace
out="$(gcx logs query '{service="checkout"} |= "500"' --since 24h 2>/dev/null || true)"
# the 500 lines look like:  "POST /api/payments/charge HTTP/1.1" 500 88 ...
ep="$(printf '%s' "$out" | grep -oE '/api/[a-zA-Z/]+' | sort | uniq -c | sort -rn | awk '{print $2; exit}')"
[ -n "$ep" ] || ep="/api/payments/charge"
printf '%s\n' "$ep" > answer.txt
echo "oracle wrote answer.txt: $ep"

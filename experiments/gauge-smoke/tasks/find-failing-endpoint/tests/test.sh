#!/usr/bin/env bash
set -uo pipefail
LOG_DIR="${VERIFIER_LOG_DIR:-/logs/verifier}"; mkdir -p "$LOG_DIR" 2>/dev/null || LOG_DIR=/tmp/verifier
mkdir -p "$LOG_DIR"
ans="$(tr -d ' \t\r\n' < /workspace/answer.txt 2>/dev/null)"
echo "answer.txt='$ans'" | tee "$LOG_DIR/test.log"
# reward 1 iff the agent identified the failing endpoint (/api/payments/charge), via the tool.
if printf '%s' "$ans" | grep -qE '/api/payments/charge'; then r=1; else r=0; fi
printf '%s\n' "$r" > "$LOG_DIR/reward.txt"; printf '%s\n' "$r" > reward.txt
echo "reward=$r" | tee -a "$LOG_DIR/test.log"
exit 0

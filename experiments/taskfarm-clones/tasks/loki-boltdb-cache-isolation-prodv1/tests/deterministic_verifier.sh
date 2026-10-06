#!/usr/bin/env bash
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd /app/src || exit 1
for tool in python3 psql; do
  command -v "$tool" >/dev/null 2>&1 || { echo "$tool missing"; exit 1; }
done
passed=true
python3 "$SCRIPT_DIR/deterministic/check_config_behavior.py" || passed=false
python3 "$SCRIPT_DIR/deterministic/check_artifact_and_db.py" || passed=false
python3 "$SCRIPT_DIR/deterministic/check_ticket_state.py" || passed=false
if [ "$passed" = true ]; then
  exit 0
fi
exit 1

#!/usr/bin/env bash
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd /app/src || exit 1
command -v psql >/dev/null || exit 1
command -v python3 >/dev/null || exit 1
passed=true
python3 "$SCRIPT_DIR/deterministic/check_behavior.py" || passed=false
python3 "$SCRIPT_DIR/deterministic/check_artifact_and_db.py" || passed=false
python3 "$SCRIPT_DIR/deterministic/check_ticket_state.py" || passed=false
if [ "$passed" = true ]; then
  exit 0
fi
exit 1

#!/usr/bin/env bash
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DET_DIR="$SCRIPT_DIR/deterministic"
LOG_DIR="${VERIFIER_LOG_DIR:-/logs/verifier}"
if ! mkdir -p "$LOG_DIR" 2>/dev/null; then
  LOG_DIR="${TMPDIR:-/tmp}/verifier"
  mkdir -p "$LOG_DIR"
fi
DET_LOG="$LOG_DIR/deterministic_checks.log"
DET_REPORT="$LOG_DIR/deterministic_report.json"

printf '{"passed":false,"steps":[],"error":"deterministic verifier did not finish"}\n' > "$DET_REPORT"
rm -f "$DET_LOG"

if ! cd /app/src 2>/dev/null; then
  printf '{"passed":false,"steps":[],"error":"missing /app/src"}\n' > "$DET_REPORT"
  exit 0
fi

export PYTHONPATH=/app/src:$DET_DIR${PYTHONPATH:+:$PYTHONPATH}

steps=(
  "hidden-tests:test_hidden.py"
  "replay-artifact:check_artifact.py"
  "github-state:check_github.py"
  "ticket-state:check_ticket_state.py"
  "slack-state:check_slack.py"
)

passed=true
step_json=""
for item in "${steps[@]}"; do
  name="${item%%:*}"
  script="${item#*:}"
  echo "== $name ==" >> "$DET_LOG"
  if python3 "$DET_DIR/$script" >> "$DET_LOG" 2>&1; then
    status="pass"
    rc=0
  else
    status="fail"
    rc=$?
    passed=false
  fi
  entry="{\"name\":\"$name\",\"script\":\"$script\",\"status\":\"$status\",\"returncode\":$rc}"
  if [ -z "$step_json" ]; then
    step_json="$entry"
  else
    step_json="$step_json,$entry"
  fi
done

if [ "$passed" = true ]; then
  printf '{"passed":true,"steps":[%s]}\n' "$step_json" > "$DET_REPORT"
else
  printf '{"passed":false,"steps":[%s]}\n' "$step_json" > "$DET_REPORT"
fi

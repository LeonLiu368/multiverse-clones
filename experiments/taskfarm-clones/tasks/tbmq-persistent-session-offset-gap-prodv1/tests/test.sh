#!/usr/bin/env bash
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${VERIFIER_LOG_DIR:-/logs/verifier}"
SCORING_MODE="binary"
mkdir -p "$LOG_DIR" 2>/dev/null || LOG_DIR="${TMPDIR:-/tmp}/verifier"
mkdir -p "$LOG_DIR"

printf '{"reward":0}\n' > "$LOG_DIR/reward.json"
printf '0\n' > "$LOG_DIR/reward.txt"
printf '{"partial_score":0.0}\n' > "$LOG_DIR/metrics.json"
printf '0\n' > reward.txt

if ! command -v nodejs >/dev/null 2>&1; then
  echo "missing required verifier tool: nodejs" > "$LOG_DIR/test.log"
  exit 0
fi
if ! command -v psql >/dev/null 2>&1; then
  echo "missing required verifier tool: psql" > "$LOG_DIR/test.log"
  exit 0
fi

if bash "$SCRIPT_DIR/deterministic_verifier.sh" > "$LOG_DIR/test.log" 2>&1; then
  printf '{"reward":1}\n' > "$LOG_DIR/reward.json"
  printf '1\n' > "$LOG_DIR/reward.txt"
  printf '{"partial_score":1.0}\n' > "$LOG_DIR/metrics.json"
  printf '1\n' > reward.txt
else
  printf '0\n' > reward.txt
fi

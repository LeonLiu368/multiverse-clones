#!/usr/bin/env bash
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${VERIFIER_LOG_DIR:-/logs/verifier}"
mkdir -p "$LOG_DIR" 2>/dev/null || LOG_DIR="${TMPDIR:-/tmp}/verifier"
mkdir -p "$LOG_DIR"
SCORING_MODE="binary"
command -v psql >/dev/null || { printf '{"reward":0}\n' > "$LOG_DIR/reward.json"; printf '0\n' > "$LOG_DIR/reward.txt"; printf '{"partial_score":0.0}\n' > "$LOG_DIR/metrics.json"; printf '0\n' > reward.txt; exit 1; }
printf '{"reward":0}\n' > "$LOG_DIR/reward.json"
printf '0\n' > "$LOG_DIR/reward.txt"
printf '{"partial_score":0.0}\n' > "$LOG_DIR/metrics.json"
printf '0\n' > reward.txt
if uv run bash "$SCRIPT_DIR/deterministic_verifier.sh" > "$LOG_DIR/test.log" 2>&1; then
  printf '{"reward":1}\n' > "$LOG_DIR/reward.json"
  printf '1\n' > "$LOG_DIR/reward.txt"
  printf '{"partial_score":1.0}\n' > "$LOG_DIR/metrics.json"
  printf '1\n' > reward.txt
  exit 0
else
  printf '0\n' > reward.txt
  exit 1
fi

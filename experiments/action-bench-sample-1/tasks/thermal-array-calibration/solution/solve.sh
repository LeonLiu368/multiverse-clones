#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${TASK_APP_DIR:-/app}"
mkdir -p "$APP_DIR"
WORK_DIR="$(mktemp -d)"

arrayctl manual > "$WORK_DIR/manual.txt"
arrayctl history > "$WORK_DIR/history.txt"
arrayctl inventory > "$WORK_DIR/inventory.txt"
arrayctl criteria > "$WORK_DIR/criteria.txt"
arrayctl schema > "$WORK_DIR/schema.txt"
arrayctl reference --setpoint ambient >> "$WORK_DIR/references.jsonl"
arrayctl reference --setpoint mid >> "$WORK_DIR/references.jsonl"
arrayctl reference --setpoint hot >> "$WORK_DIR/references.jsonl"
arrayctl baseline --setpoint ambient >> "$WORK_DIR/baselines.jsonl"
arrayctl baseline --setpoint mid >> "$WORK_DIR/baselines.jsonl"
arrayctl baseline --setpoint hot >> "$WORK_DIR/baselines.jsonl"
for probe in P1 P2 P3 P4 P5; do
  arrayctl measure --probe "$probe" --setpoint ambient --mode stable >> "$WORK_DIR/measurements.jsonl"
done
for setpoint in mid hot; do
  for probe in P2 P3 P4 P5; do
    arrayctl measure --probe "$probe" --setpoint "$setpoint" --mode stable >> "$WORK_DIR/measurements.jsonl"
  done
done

python3 "$(dirname "$0")/derive_calibration.py" "$WORK_DIR/measurements.jsonl" "$WORK_DIR/references.jsonl" "$WORK_DIR/baselines.jsonl" "$APP_DIR/calibration.json"

arrayctl submit --file "$APP_DIR/calibration.json" >/dev/null

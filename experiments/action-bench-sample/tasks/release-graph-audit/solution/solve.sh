#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${TASK_APP_DIR:-/app}"
mkdir -p "$APP_DIR"
WORK_DIR="$(mktemp -d)"
SOLUTION_DIR="$(cd "$(dirname "$0")" && pwd)"

releasectl docs > "$WORK_DIR/docs.md"
releasectl schema > "$WORK_DIR/schema.txt"
releasectl list --state open > "$WORK_DIR/open-items.json"
releasectl gates --train REL-884 > "$WORK_DIR/gates.json"

python3 "$SOLUTION_DIR/build_handoff.py" candidates "$WORK_DIR/open-items.json" > "$WORK_DIR/candidate-ids.txt"
python3 "$SOLUTION_DIR/build_handoff.py" gates "$WORK_DIR/gates.json" >> "$WORK_DIR/candidate-ids.txt"
while IFS= read -r id; do
  [ -n "$id" ] || continue
  releasectl get --id "$id" > "$WORK_DIR/$id.json"
done < "$WORK_DIR/candidate-ids.txt"

python3 "$SOLUTION_DIR/build_handoff.py" preliminary "$WORK_DIR" > "$WORK_DIR/preliminary-ids.txt"
while IFS= read -r id; do
  [ -n "$id" ] || continue
  releasectl checks --id "$id" > "$WORK_DIR/$id.checks.json"
  releasectl reviews --id "$id" > "$WORK_DIR/$id.reviews.json"
  releasectl links --id "$id" > "$WORK_DIR/$id.links.json"
  [ -f "$WORK_DIR/$id.decisions.json" ] || releasectl decisions --id "$id" > "$WORK_DIR/$id.decisions.json"
done < "$WORK_DIR/preliminary-ids.txt"

python3 "$SOLUTION_DIR/build_handoff.py" followups "$WORK_DIR" > "$WORK_DIR/followup-ids.txt"
while IFS= read -r id; do
  [ -n "$id" ] || continue
  [ -f "$WORK_DIR/$id.json" ] && continue
  releasectl get --id "$id" > "$WORK_DIR/$id.json"
  releasectl checks --id "$id" > "$WORK_DIR/$id.checks.json"
  releasectl reviews --id "$id" > "$WORK_DIR/$id.reviews.json"
  releasectl links --id "$id" > "$WORK_DIR/$id.links.json"
  releasectl decisions --id "$id" > "$WORK_DIR/$id.decisions.json"
done < "$WORK_DIR/followup-ids.txt"

python3 "$SOLUTION_DIR/build_handoff.py" handoff "$WORK_DIR" "$APP_DIR/release_handoff.json"

releasectl submit --file "$APP_DIR/release_handoff.json" >/dev/null

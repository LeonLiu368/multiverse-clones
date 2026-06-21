#!/usr/bin/env bash
# jira-boot.sh — boot pre-processor for the ticketvector-backed jira-gateway.
#
# Why this exists: ticketvector loads a SINGLE state.json at boot
# (FakePlaneBackend._load). A bind mount over /var/lib/ticketvector/state.json
# only SHADOWS the baked corpus — you cannot have the baked ENG corpus AND a
# task's own tickets. This script builds a writable runtime COPY of the baked
# state, then optionally applies:
#   * /data/state-overlay.json  — ADDITIVE merge (baked corpus + task's tickets)
#   * /data/state-patch.json    — op-list mutations of the prod corpus
# and serves THAT runtime copy, leaving the baked image frozen.
#
# Env:
#   WORLD_ISSUES_STATE_FILE  source state.json (default: the baked prod path).
set -euo pipefail

SRC="${WORLD_ISSUES_STATE_FILE:-/var/lib/ticketvector/state.json}"
RUNTIME="/tmp/state.runtime.json"

if [ ! -f "$SRC" ]; then
  echo "JIRA_BOOT_ERROR source state.json not found: $SRC" >&2
  exit 1
fi

cp "$SRC" "$RUNTIME"

OVERLAY=0
PATCH=0

if [ -f /data/state-overlay.json ]; then
  # apply_overlay normalizes first, then merges.
  python3 /opt/apply_state_patch.py --state "$RUNTIME" --overlay /data/state-overlay.json
  OVERLAY=1
else
  # No overlay: normalize the runtime copy so the prod corpus is write-faithful (it bakes
  # `history` as a list, which breaks update_issue/add_comment until coerced to a dict).
  python3 /opt/apply_state_patch.py --state "$RUNTIME" --normalize
fi

if [ -f /data/state-patch.json ]; then
  python3 /opt/apply_state_patch.py --state "$RUNTIME" --patch /data/state-patch.json
  PATCH=1
fi

ISSUES="$(python3 -c 'import json,sys; print(len(json.load(open(sys.argv[1])).get("issues",[])))' "$RUNTIME")"
echo "JIRA_BOOT overlay=${OVERLAY} patch=${PATCH} issues=${ISSUES}"

export WORLD_ISSUES_STATE_FILE="$RUNTIME"
exec python -m world_issues.server

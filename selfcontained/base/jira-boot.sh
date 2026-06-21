#!/usr/bin/env bash
# jira-boot.sh — boot pre-processor for the ticketvector-backed jira-gateway.
#
# ONE mount path, both images. A task always mounts its state.json at
#   /data/state-overlay.json
# and switches between an empty workspace and the prod corpus by changing ONLY the
# image (jira-gateway:empty vs :prod-v1). The boot decides base-vs-overlay by
# whether the image has a baked corpus:
#   * :prod-v1 (baked corpus present) → corpus is the BASE, the mount is MERGED on top.
#   * :empty   (no baked corpus)      → the mount IS the base workspace.
# The result is served from a writable /tmp copy, so the baked image stays frozen.
# An optional /data/state-patch.json applies op-list mutations after that.
#
# Env:
#   WORLD_ISSUES_STATE_FILE  baked corpus path to look for (default: the prod path).
set -euo pipefail

BAKED="${WORLD_ISSUES_STATE_FILE:-/var/lib/ticketvector/state.json}"
MOUNT="/data/state-overlay.json"   # the task's state.json (base on :empty, overlay on :prod-v1)
PATCHF="/data/state-patch.json"
RUNTIME="/tmp/state.runtime.json"

if [ -f "$BAKED" ]; then
  # prod-v1: the baked corpus is the base; the mounted state.json (if any) is an overlay.
  cp "$BAKED" "$RUNTIME"
  if [ -f "$MOUNT" ]; then
    python3 /opt/apply_state_patch.py --state "$RUNTIME" --overlay "$MOUNT"   # normalizes then merges
    MODE="prod+overlay"
  else
    python3 /opt/apply_state_patch.py --state "$RUNTIME" --normalize
    MODE="prod"
  fi
elif [ -f "$MOUNT" ]; then
  # empty: no baked corpus, so the mounted state.json IS the base workspace.
  cp "$MOUNT" "$RUNTIME"
  python3 /opt/apply_state_patch.py --state "$RUNTIME" --normalize
  MODE="empty+mounted"
else
  echo "JIRA_BOOT_ERROR no state found: neither baked ($BAKED) nor mounted ($MOUNT)" >&2
  exit 1
fi

if [ -f "$PATCHF" ]; then
  python3 /opt/apply_state_patch.py --state "$RUNTIME" --patch "$PATCHF"
  MODE="${MODE}+patch"
fi

ISSUES="$(python3 -c 'import json,sys; print(len(json.load(open(sys.argv[1])).get("issues",[])))' "$RUNTIME")"
echo "JIRA_BOOT mode=${MODE} issues=${ISSUES}"

export WORLD_ISSUES_STATE_FILE="$RUNTIME"
exec python -m world_issues.server

#!/usr/bin/env bash
# Fetch this task's APEX fixtures from HF, convert to clone seeds, write to the mounted
# named volumes (/out/{ticketvector,slack,gauge}). Idempotent: skips if already seeded.
set -euo pipefail

TASK="${APEX_TASK:?APEX_TASK required}"     # e.g. Observability/<task-dir>
SERVICE="${APEX_SERVICE:-service}"
KEY="${APEX_KEY:-OPS}"
WORKSPACE="${APEX_WORKSPACE:-meridian}"

if [ -f /out/ticketvector/state.json ] && [ -f /out/slack/scraped.json ] && [ -f /out/gauge/state.json ]; then
  echo "seeds already present, skipping"; exit 0
fi

python - "$TASK" <<'PY'
import sys
from huggingface_hub import snapshot_download
task = sys.argv[1]
snapshot_download(repo_id="mercor/APEX-SWE", repo_type="dataset",
                  allow_patterns=[f"{task}/data/**"], local_dir="/tmp/apex")
PY

B="/tmp/apex/${TASK}/data"
LOG="$(ls "$B"/loki/*.log 2>/dev/null | head -1 || true)"
[ -n "$LOG" ] || LOG="$B/loki/logs.json"

# Load-bearing variant: splice the authored webhook-SSRF incident into the request logs so the
# attack vectors + the agreed config interface live ONLY in gauge (not in the instruction).
if [ -f /seed/incident-webhook-ssrf.log ] && [ -n "$LOG" ] && [ -f "$LOG" ]; then
  cat /seed/incident-webhook-ssrf.log >> "$LOG"
  echo "spliced webhook-SSRF incident into $LOG"
fi

python /seed/apex_to_clones.py \
  --plane "$B/plane/issues.json" \
  --mattermost "$B/mattermost/scraped.json" \
  --loki "$LOG" \
  --service "$SERVICE" --project-key "$KEY" --workspace "$WORKSPACE" \
  --out /out

echo "seed complete:"
ls -la /out/ticketvector /out/slack /out/gauge

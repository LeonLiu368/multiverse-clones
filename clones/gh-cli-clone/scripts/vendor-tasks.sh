#!/usr/bin/env bash
# Copy shared self-contained bits into each oddish task's build context so each is
# standalone. Actions tasks (Dockerfile COPYs forge-up-actions.sh) get the runner
# variant; the rest get the plain forge-up.sh.
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
for t in "$HERE"/examples/oddish-tasks/*/; do
  [ -d "$t/environment" ] || continue
  rm -rf "$t/environment/ghclone"; cp -r "$HERE/ghclone" "$t/environment/ghclone"
  if grep -q "forge-up-actions.sh" "$t/environment/Dockerfile" 2>/dev/null; then
    cp "$HERE/selfcontained/forge-up-actions.sh" "$t/environment/forge-up-actions.sh"
  else
    cp "$HERE/selfcontained/forge-up.sh" "$t/environment/forge-up.sh"
  fi
done
echo "vendored into $(ls -d "$HERE"/examples/oddish-tasks/*/ | wc -l | tr -d ' ') tasks"

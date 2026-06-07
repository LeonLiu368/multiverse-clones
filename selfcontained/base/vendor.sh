#!/usr/bin/env bash
# Vendor the per-task build files from this single source into every task's environment/.
#
# Tasks pull the prebuilt slack-service image for `api`, but Harbor force-builds the `main` (agent)
# service from environment/Dockerfile — so each task must carry the thin agent Dockerfile, its
# entrypoint, the compose, and .dockerignore. They are NOT the heavy backend (that's the pulled
# image); they're small and identical across tasks. Edit them ONCE here, then run this script.
#
#   selfcontained/base/vendor.sh
#
# data/ and codebase/ are task-owned and never touched. The compose's __TASK__ placeholder is
# replaced with the task name so each task keeps a unique local agent image tag.
set -euo pipefail
cd "$(dirname "$0")"
BASE="$(pwd)"
TASKS_DIR="$(cd ../../oddish/tasks && pwd)"
VERBATIM=(Dockerfile main-entrypoint.sh .dockerignore)
for taskpath in "$TASKS_DIR"/*/; do
  task="$(basename "$taskpath")"
  env="$taskpath/environment"
  [ -d "$env" ] || continue
  for f in "${VERBATIM[@]}"; do
    rm -rf "$env/${f:?}"
    cp -R "$BASE/$f" "$env/$f"
  done
  sed "s/__TASK__/$task/g" "$BASE/docker-compose.yaml" > "$env/docker-compose.yaml"
  echo "vendored -> $task"
done
echo "done. (slack CLI + MCP are baked in slack-service; data/ and codebase/ are task-owned and untouched.)"

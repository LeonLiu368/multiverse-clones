#!/usr/bin/env bash
# Vendor the shared build files from this single source into every task's environment/.
#
# Tasks are SELF-CONTAINED (the harness builds each task's Dockerfile, with the task dir as the
# build context — it cannot pull files from outside the task). So the gateway, seeder, entrypoints,
# Dockerfiles, and compose must physically exist in each task. Rather than hand-maintain copies,
# edit them ONCE here and run this script to push them into every task.
#
#   selfcontained/base/vendor.sh
#
# Re-run after changing anything in selfcontained/base/. The per-task codebase/ and data/ are NOT
# touched. The compose is templated: __TASK__ is replaced with the task name so each task keeps a
# unique local image tag (avoids cross-task image collisions in local `docker compose up`).
set -euo pipefail
cd "$(dirname "$0")"
BASE="$(pwd)"
TASKS_DIR="$(cd ../../oddish/tasks && pwd)"

# Files copied verbatim (byte-identical across all tasks).
VERBATIM=(slackgw seed.py api-entrypoint.sh main-entrypoint.sh seed.sh Dockerfile.api Dockerfile.main .dockerignore)

for taskpath in "$TASKS_DIR"/*/; do
  task="$(basename "$taskpath")"
  env="$taskpath/environment"
  [ -d "$env" ] || continue
  for f in "${VERBATIM[@]}"; do
    rm -rf "$env/${f:?}"
    cp -R "$BASE/$f" "$env/$f"
  done
  # compose: substitute the task name for the templated image tags.
  sed "s/__TASK__/$task/g" "$BASE/docker-compose.yaml" > "$env/docker-compose.yaml"
  echo "vendored -> $task"
done
echo "done. (codebase/ and data/ are task-owned and untouched.)"

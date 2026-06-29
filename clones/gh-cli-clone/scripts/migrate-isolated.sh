#!/usr/bin/env bash
# Migrate single-container tasks to the 2-container isolated layout (agent in
# `main`, git host in the `api` sidecar). Idempotent + re-runnable: it also acts
# as the re-vendor step (sync scaffold + ghclone) for already-migrated tasks.
#
# For each task with an environment/ dir it:
#   - copies the shared scaffold (docker-compose.yaml, Dockerfile.main,
#     Dockerfile.forge, forge-entrypoint.sh) — actions tasks get the runner flavor
#   - vendors ghclone into the sidecar build context
#   - drops the old single-container files (Dockerfile, forge-up*.sh)
#   - renames the repo owner ghc-admin -> acme in task-visible files
#   - rewrites task.toml to compose mode (healthcheck `gh auth status`)
set -uo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
ISO="$HERE/selfcontained/isolated"
# The self-contained/isolated suite. examples/tasks/ is the legacy external-forge
# demo (FROM ghc-agent:local, seeded via scripts/up.sh) and is intentionally
# excluded — it has no per-task seed.sh to bundle into a sidecar.
TASK_GLOBS=("$HERE/examples/oddish-tasks")

is_actions(){ # actions task if it seeds/exercises a workflow — stable across re-runs
  grep -rqi "workflow\|upload-artifact\|gh run \|gh workflow\|actions/runs\|actions/tasks\|\"actions\"" \
    "$1/environment/seed.sh" "$1/tests" "$1/solution" "$1/task.toml" 2>/dev/null
}

migrate(){
  local t="$1" name; name="$(basename "$t")"
  [ -d "$t/environment" ] || return 0
  # incident-isolated is hand-built but uses the same scaffold — keep it in sync.

  local actions=0; is_actions "$t" && actions=1
  echo ">> $name $([ $actions = 1 ] && echo '(actions)')"

  # 1. scaffold
  cp "$ISO/docker-compose.yaml" "$t/environment/docker-compose.yaml"
  cp "$ISO/Dockerfile.main"     "$t/environment/Dockerfile.main"
  cp "$ISO/main-entrypoint.sh"  "$t/environment/main-entrypoint.sh"
  if [ "$actions" = 1 ]; then
    cp "$ISO/Dockerfile.forge-actions"     "$t/environment/Dockerfile.forge"
    cp "$ISO/forge-entrypoint-actions.sh"  "$t/environment/forge-entrypoint.sh"
  else
    cp "$ISO/Dockerfile.forge"   "$t/environment/Dockerfile.forge"
    cp "$ISO/forge-entrypoint.sh" "$t/environment/forge-entrypoint.sh"
  fi

  # 2. vendor ghclone (gitignored)
  rm -rf "$t/environment/ghclone"; cp -r "$HERE/ghclone" "$t/environment/ghclone"
  find "$t/environment/ghclone" -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null

  # 3. drop single-container leftovers
  rm -f "$t/environment/Dockerfile" "$t/environment/forge-up.sh" "$t/environment/forge-up-actions.sh"

  # 4. neutral owner in task-visible files (not the vendored ghclone)
  for f in "$t/environment/seed.sh" "$t/instruction.md" "$t/tests/test.sh" "$t/solution/solve.sh"; do
    [ -f "$f" ] && sed -i '' 's/ghc-admin/acme/g' "$f"
  done

  # 5. task.toml -> compose mode (idempotent rewrite)
  python3 - "$t/task.toml" <<'PY'
import re, sys, pathlib
p = pathlib.Path(sys.argv[1]); s = p.read_text()
# drop the single-container build hint (compose mode auto-triggers on the yaml)
s = re.sub(r'^\s*build_strategy\s*=.*\n', '', s, flags=re.M)
# normalize the healthcheck block to the proven isolated values (gates on the
# sidecar having seeded the token; the pyinstaller build runs in the build step)
s = re.sub(
    r'\[environment\.healthcheck\].*?(?=\n\[|\Z)',
    '[environment.healthcheck]\n'
    'command = "gh auth status"\n'
    'interval_sec = 5.0\n'
    'timeout_sec = 30.0\n'
    'start_period_sec = 15.0\n'
    'retries = 60\n',
    s, flags=re.S)
# the multi-stage build (pyinstaller + two images) needs headroom
s = re.sub(r'build_timeout_sec\s*=\s*[0-9.]+',
           'build_timeout_sec = 2400.0', s)
# sidecar reachability needs the bridge (not network_mode:none)
if 'allow_internet' in s:
    s = re.sub(r'allow_internet\s*=\s*\w+', 'allow_internet = true', s)
else:
    s = s.replace('[environment]\n', '[environment]\nallow_internet = true\n', 1)
p.write_text(s.rstrip()+'\n')
PY
}

for g in "${TASK_GLOBS[@]}"; do
  [ -d "$g" ] || continue
  for t in "$g"/*/; do migrate "${t%/}"; done
done
echo "done."

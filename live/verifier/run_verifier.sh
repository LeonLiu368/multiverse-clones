#!/bin/bash
# Harbor wrapper for the shared soak/SLO verifier (Primitive P3).
#
# Runs INSIDE the `main` container AFTER the agent exits. It resolves the SUT
# target + soak config from env/task, copies soak.py into an isolated /tmp/grade
# dir (so the agent's workspace cannot shadow it), runs the soak, and GUARANTEES
# a reward.txt is written even if soak.py crashes (0 + infra_error on crash).
#
# Mirrors the isolation + reward.txt contract of the slack incident verifier:
#   * copies the grader out of the workspace before running
#   * writes ${REWARD_DIR:-/logs/verifier}/reward.txt (a bare float)
#   * honors REWARD_DIR override so it runs locally without a container
#
# Task wires these via env (or edit the defaults):
#   SOAK_TARGET   e.g. http://conduit.web.1:5000   (the SUT container name:port)
#   SOAK_CONFIG   path to the task's soak config JSON (defaults next to this file)
#   FINDINGS_PATH path to the agent's findings.json (default /workspace/findings.json)
#   AUDIT_CMD     optional shell cmd to snapshot the final deploy config
#   AUDIT_FILE    optional path to a pre-captured deploy snapshot
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REWARD_DIR="${REWARD_DIR:-/logs/verifier}"
export REWARD_DIR
mkdir -p "$REWARD_DIR"

TARGET="${SOAK_TARGET:-http://conduit.web.1:5000}"
CONFIG="${SOAK_CONFIG:-$HERE/soak_config.example.json}"
FINDINGS="${FINDINGS_PATH:-/workspace/findings.json}"

# Isolate the grader from the agent's workspace: copy soak.py to /tmp/grade.$$
GRADE="/tmp/grade.$$"
rm -rf "$GRADE"; mkdir -p "$GRADE"
cp "$HERE/soak.py" "$GRADE/soak.py"
# Copy the config too, so a workspace-resident config can't be swapped mid-run.
CONFIG_COPY="$GRADE/soak_config.json"
if ! cp "$CONFIG" "$CONFIG_COPY" 2>/dev/null; then
  # No config resolvable -> infra error, explicit reward 0.
  echo "0.0" > "$REWARD_DIR/reward.txt"
  printf '{"infra_error": true, "reason": "soak config not found: %s"}\n' "$CONFIG" \
    > "$REWARD_DIR/result.json"
  echo "run_verifier: soak config not found ($CONFIG) -> reward 0 (infra_error)"
  rm -rf "$GRADE"
  exit 0
fi

PY="${PYTHON:-python3}"

ARGS=(--target "$TARGET" --config "$CONFIG_COPY"
      --reward-dir "$REWARD_DIR" --findings "$FINDINGS")
[ -n "${AUDIT_CMD:-}" ]  && ARGS+=(--audit-cmd  "$AUDIT_CMD")
[ -n "${AUDIT_FILE:-}" ] && ARGS+=(--audit-file "$AUDIT_FILE")

echo "run_verifier: target=$TARGET config=$CONFIG findings=$FINDINGS reward_dir=$REWARD_DIR"

set +e
( cd "$GRADE" && "$PY" soak.py "${ARGS[@]}" )
rc=$?
set -e

# Infra failure contract: soak.py exits NONZERO *without* writing reward.txt when
# the environment was never usable (dead target, crashed cluster, verifier bug).
# Propagate that exit code so the harness records a trial ERROR (retryable on a
# fresh sandbox) instead of scraping a false 0. Only a genuine graded run (rc=0)
# leaves a reward.txt behind.
if [ "$rc" -ne 0 ]; then
  echo "run_verifier: INFRA ERROR (rc=$rc) -> propagating as trial error (no reward)"
  rm -f "$REWARD_DIR/reward.txt"
  rm -rf "$GRADE"
  exit "$rc"
fi

echo "run_verifier: reward=$(cat "$REWARD_DIR/reward.txt" 2>/dev/null)"
rm -rf "$GRADE"
exit 0

#!/usr/bin/env bash
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${VERIFIER_LOG_DIR:-/logs/verifier}"
if ! mkdir -p "$LOG_DIR" 2>/dev/null; then
  LOG_DIR="${TMPDIR:-/tmp}/verifier"
  mkdir -p "$LOG_DIR"
fi
VERIFIER_DIR="/verifier"
mkdir -p "$VERIFIER_DIR" 2>/dev/null || VERIFIER_DIR=""
TEST_LOG="$LOG_DIR/test.log"

# verifier runs as root against the agent-owned repo: trust it for git,
# and keep git/gh non-interactive
git config --global --add safe.directory '*' 2>/dev/null || true
export GIT_TERMINAL_PROMPT=0 GIT_PAGER=cat GH_PAGER=cat

write_reward_json() {
  local value="$1"
  printf '{"reward":%s}\n' "$value" > "$LOG_DIR/reward.json"
  printf '%s\n' "$value" > "$LOG_DIR/reward.txt"
  printf '{"reward":%s}\n' "$value" > reward.json 2>/dev/null || true
  printf '%s\n' "$value" > reward.txt 2>/dev/null || true
  if [ -n "$VERIFIER_DIR" ]; then
    printf '{"reward":%s}\n' "$value" > "$VERIFIER_DIR/reward.json" 2>/dev/null || true
    printf '%s\n' "$value" > "$VERIFIER_DIR/reward.txt" 2>/dev/null || true
  fi
}

rm -f reward.txt reward.json "$LOG_DIR/reward.txt" "$LOG_DIR/reward.json" "$TEST_LOG"
if [ -n "$VERIFIER_DIR" ]; then
  rm -f "$VERIFIER_DIR/reward.txt" "$VERIFIER_DIR/reward.json"
fi
write_reward_json 0

export PYTHONPATH=/app/src:$SCRIPT_DIR/deterministic${PYTHONPATH:+:$PYTHONPATH}

echo "== collect evidence ==" >> "$TEST_LOG"
python3 "$SCRIPT_DIR/collect_evidence.py" >> "$TEST_LOG" 2>&1 || true

# The judge CLI is a verifier-only dependency: install it here at verification
# time (version-pinned, sha256-verified), never in the agent image.
CURSOR_AGENT_VERSION="2026.06.04-5fd875e"
CURSOR_AGENT_SHA256="5425aab29f8a01d377de3dc7f7455739ad59829e0879ea0c4296bd9eec520300"
if ! command -v cursor-agent >/dev/null 2>&1; then
  echo "== install judge cli ==" >> "$TEST_LOG"
  {
    curl -fsSL "https://downloads.cursor.com/lab/${CURSOR_AGENT_VERSION}/linux/x64/agent-cli-package.tar.gz" -o /tmp/cursor-agent.tgz \
      && echo "${CURSOR_AGENT_SHA256}  /tmp/cursor-agent.tgz" | sha256sum -c - \
      && mkdir -p /opt/cursor-judge \
      && tar -xzf /tmp/cursor-agent.tgz -C /opt/cursor-judge \
      && rm -f /tmp/cursor-agent.tgz \
      && ln -sf /opt/cursor-judge/dist-package/cursor-agent /usr/local/bin/cursor-agent \
      && cursor-agent --version
  } >> "$TEST_LOG" 2>&1 || echo "judge cli install failed; agent_judge.py will fail closed" >> "$TEST_LOG"
fi

echo "== agent judge ==" >> "$TEST_LOG"
python3 "$SCRIPT_DIR/agent_judge.py" >> "$TEST_LOG" 2>&1 || true

python3 - "$LOG_DIR" "$VERIFIER_DIR" <<'PY'
import json
import os
import sys
from pathlib import Path

log_dir = Path(sys.argv[1])
verifier_dir = Path(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2] else None
log_dir.mkdir(parents=True, exist_ok=True)
reward_path = log_dir / "reward.json"

def reset():
    reward_path.write_text('{"reward":0}\n')

try:
    data = json.loads(reward_path.read_text())
    value = data["reward"]
    mode = os.environ.get("REWARD_MODE", "binary").lower()
    if mode != "continuous" and os.environ.get("ALLOW_FRACTIONAL_LLM_REWARD") != "1":
        if value not in (0, 1):
            reset()
            value = 0
    elif not isinstance(value, (int, float)) or value < 0 or value > 1:
        reset()
        value = 0
except Exception:
    reset()
    value = 0

for filename, default in {
    "evidence.json": {"status": "missing", "error": "evidence collector did not produce evidence"},
    "judge_report.json": {"status": "missing", "error": "judge did not produce a report"},
}.items():
    path = log_dir / filename
    if not path.exists():
        path.write_text(json.dumps(default, sort_keys=True) + "\n")

text_value = str(value)
(log_dir / "reward.txt").write_text(text_value + "\n")
Path("reward.json").write_text(reward_path.read_text())
Path("reward.txt").write_text(text_value + "\n")
if verifier_dir:
    try:
        verifier_dir.mkdir(parents=True, exist_ok=True)
        (verifier_dir / "reward.json").write_text(reward_path.read_text())
        (verifier_dir / "reward.txt").write_text(text_value + "\n")
    except Exception:
        pass
PY

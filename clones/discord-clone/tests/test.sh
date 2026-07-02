#!/usr/bin/env bash
# Clone unit suite runner (R6.4): green from a cold start; writes a reward.
#
#   * Always: run the endpoint + CLI + MCP + parity suite against an in-process
#     gateway seeded from the deterministic generator (needs only the Python deps).
#   * With docker: additionally build the THIN agent image and run the isolation
#     suite (R6.3/R2.k) against it — data-free, seed/api not importable, no source.
#
# Honors REWARD_DIR so nop/oracle-style local runs work without /logs mounted.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
cd "$ROOT"
rc=1

reward() {
  local r="${1:-0}"
  local dir="${REWARD_DIR:-/logs/verifier}"
  mkdir -p "$dir" 2>/dev/null || true
  echo "$r" > "$dir/reward.txt" 2>/dev/null || true
}

# Pick a python with the package installed. Prefer the project venv.
if [ -x "$ROOT/.venv/bin/python" ]; then
  PY="$ROOT/.venv/bin/python"
else
  PY="python3"
  "$PY" -c "import discordclone" 2>/dev/null || pip install -q -e "$ROOT[dev]" >/dev/null 2>&1 || true
fi

echo "[test] running endpoint/CLI/MCP/parity suite (in-process gateway)"
"$PY" -m pytest -q "$HERE/test_api.py" "$HERE/test_cli_mcp_parity.py" -p no:cacheprovider
core_rc=$?

iso_rc=0
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  echo "[test] docker available — building the thin agent image + running isolation suite"
  AGENT="${DISCORD_AGENT_IMAGE:-ghcr.io/abundant-ai/discord-agent:test}"
  docker build -t "$AGENT" -f "$ROOT/docker/Dockerfile.agent" "$ROOT" >/dev/null
  DISCORD_AGENT_IMAGE="$AGENT" "$PY" -m pytest -q "$HERE/test_isolation.py" -p no:cacheprovider
  iso_rc=$?
else
  echo "[test] no docker — isolation suite skips (built agent image unavailable)"
fi

[ "$core_rc" -eq 0 ] && [ "$iso_rc" -eq 0 ] && rc=0 || rc=1
[ "$rc" -eq 0 ] && reward 1 || reward 0
exit "$rc"

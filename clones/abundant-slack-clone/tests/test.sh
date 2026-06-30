#!/usr/bin/env bash
# Clone unit suite runner (R6.4): green from a cold start.
#
# Strategy: the gateway image already carries python+pytest, the `slack` CLI, and the korotovsky
# `slack-mcp` binary, so the endpoint + CLI + MCP + parity suite runs INSIDE a booted gateway
# container (seeded from a deterministic export). The isolation suite (R6.3) runs from the host
# against the THIN agent image (asserting it is data-free and the seed generator isn't importable).
#
#   * With docker: build service/agent/empty-gateway, boot the gateway on the fixture export, run
#     test_endpoints/test_cli/test_mcp INSIDE it, then test_isolation against the agent image.
#   * Without docker: run the whole suite against the conftest's in-process gateway (MCP + isolation
#     skip — they need the built images). Useful for a quick local check.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
BASE="$ROOT/selfcontained/base"
TAG="${SLACK_TEST_TAG:-slack-mcp-oss}"
SVC="ghcr.io/abundant-ai/slack-service:${TAG}"
AGENT="ghcr.io/abundant-ai/slack-agent:${TAG}"
GW="ghcr.io/abundant-ai/slack-gateway:empty"
GW_NAME="slack-clone-test-gw-$$"
rc=1

cleanup() { docker rm -f "$GW_NAME" >/dev/null 2>&1 || true; }

reward() {
  local r="${1:-1}"
  local dir="${REWARD_DIR:-/logs/verifier}"
  mkdir -p "$dir" 2>/dev/null || true
  echo "$r" > "$dir/reward.txt" 2>/dev/null || true
}

if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  echo "[test] docker available — building images + booting a real gateway"
  trap cleanup EXIT
  docker build -t "$SVC"   -f "$BASE/Dockerfile.service" "$BASE" >/dev/null
  docker build -t "$AGENT" -f "$BASE/Dockerfile.agent"  --build-arg "SLACK_SERVICE=$SVC" "$BASE" >/dev/null
  docker build -t "$GW"    -f "$BASE/Dockerfile.empty"  --build-arg "SLACK_SERVICE=$SVC" "$BASE" >/dev/null

  FIX="$(mktemp -d)"
  python3 "$HERE/seed_fixture_export.py" "$FIX/slack-export"

  cleanup
  docker run -d --name "$GW_NAME" -e SLACK_TEAM=testworkspace \
    -v "$FIX/slack-export:/data/slack-export:ro" "$GW" >/dev/null
  for _ in $(seq 1 60); do
    docker exec "$GW_NAME" curl -sf "http://localhost:80/api/auth.test" >/dev/null 2>&1 && break; sleep 1
  done

  # Run the HTTP/CLI/MCP/parity suite INSIDE the gateway (it has all the tools + serves localhost).
  docker exec "$GW_NAME" mkdir -p /suite
  docker cp "$HERE/conftest.py"        "$GW_NAME:/suite/conftest.py"
  docker cp "$HERE/test_endpoints.py"  "$GW_NAME:/suite/test_endpoints.py"
  docker cp "$HERE/test_cli.py"        "$GW_NAME:/suite/test_cli.py"
  docker cp "$HERE/test_mcp.py"        "$GW_NAME:/suite/test_mcp.py"
  docker exec -e SLACK_TEST_URL="http://localhost:80" \
              -e SLACK_API_URL="http://localhost" \
              -e SLACK_BOT_TOKEN="xoxp-acme-eval-0001" \
              -e PYTHONPATH="/suite:/opt/slackcli" \
              "$GW_NAME" python3 -m pytest -q /suite -p no:cacheprovider
  in_rc=$?

  # Isolation (R6.3): probe the THIN agent image from the host (the test shells out to `docker run`).
  # Needs a python with pytest; use the host's if present, else a throwaway venv.
  if python3 -c "import pytest" >/dev/null 2>&1; then
    ISO_PY=python3
  else
    VENV="$(mktemp -d)/venv"
    python3 -m venv "$VENV" >/dev/null 2>&1 && "$VENV/bin/pip" -q install pytest >/dev/null 2>&1
    ISO_PY="$VENV/bin/python"
  fi
  SLACK_AGENT_IMAGE="$AGENT" "$ISO_PY" -m pytest -q "$HERE/test_isolation.py" -p no:cacheprovider
  iso_rc=$?

  [ "$in_rc" -eq 0 ] && [ "$iso_rc" -eq 0 ] && rc=0 || rc=1
else
  echo "[test] no docker — running against the in-process gateway (MCP + isolation skip)"
  PYTHONPATH="$BASE/slackcli" python3 -m pytest -q "$HERE" -p no:cacheprovider
  rc=$?
fi

[ "$rc" -eq 0 ] && reward 1 || reward 0
exit "$rc"

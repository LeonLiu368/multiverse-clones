#!/usr/bin/env bash
# Build the three Jira-clone base images locally (native arch by default).
#   jira-gateway:prod-v1  — ticketvector service + ENG prod corpus baked in (the `jira` sidecar)
#   jira-gateway:empty    — ticketvector service, no data (mount your own state.json)
#   jira-agent:latest     — thin agent: jira/linear CLI only, no service, no data
#
# The base ghcr.io/abundant-ai/ticketvector-service:latest is linux/amd64; on arm it runs under
# emulation (verified to boot + serve). For a GHCR push, add `--platform linux/amd64,linux/arm64`
# via buildx once the base is multi-arch — see docs/IMAGE-RELEASE.md (FOLLOW-UP).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

REGISTRY="${REGISTRY:-ghcr.io/abundant-ai}"
PROD_TAG="${PROD_TAG:-prod-v1}"
# The ticketvector-service base is currently amd64-only, so pin the build platform; on arm it runs
# under emulation (verified to boot + serve). The CLI/service are pure-python so this is portable.
PLATFORM="${PLATFORM:-linux/amd64}"

echo "==> jira-gateway:${PROD_TAG} (ENG prod corpus baked)"
docker build --platform "$PLATFORM" -f Dockerfile.gateway -t "jira-gateway:${PROD_TAG}" -t "${REGISTRY}/jira-gateway:${PROD_TAG}" .

echo "==> jira-gateway:empty (no data)"
docker build --platform "$PLATFORM" -f Dockerfile.empty -t "jira-gateway:empty" -t "${REGISTRY}/jira-gateway:empty" .

echo "==> jira-agent:latest (thin agent: CLI + MCP, NO gateway API/seed source)"
# The agent build needs both these base files (Dockerfile.agent, strip_agent_tooling.py,
# agent-entrypoint.sh) AND the repo-root mcp/ package. Build from the REPO ROOT so mcp/ is in
# context; point -f at this dir's Dockerfile.agent (which COPYs `mcp` and the base scripts by path).
REPO_ROOT="$(cd "$HERE/../.." && pwd)"
docker build --platform "$PLATFORM" \
  -f "$HERE/Dockerfile.agent" \
  -t "jira-agent:latest" -t "${REGISTRY}/jira-agent:latest" \
  "$REPO_ROOT"

echo "==> done:"
docker images | grep -E 'jira-gateway|jira-agent' || true

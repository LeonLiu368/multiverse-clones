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

echo "==> jira-agent:latest (thin agent, tools only)"
docker build --platform "$PLATFORM" -f Dockerfile.agent -t "jira-agent:latest" -t "${REGISTRY}/jira-agent:latest" .

echo "==> done:"
docker images | grep -E 'jira-gateway|jira-agent' || true

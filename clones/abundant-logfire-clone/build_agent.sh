#!/usr/bin/env bash
# Build the logfire-agent (client) image — matched pair to logfire-gateway.
#   build_agent.sh <image-tag>
# Carries only the `logfire` CLI + `logfire-mcp` (no data); talks to the gateway at $LOGFIRE_URL.
set -euo pipefail
TAG="${1:?image tag, e.g. ghcr.io/abundant-ai/logfire-agent:latest}"
HERE="$(cd "$(dirname "$0")" && pwd)"
docker build --platform linux/amd64 -f "$HERE/Dockerfile.agent" -t "$TAG" "$HERE"
echo "built $TAG"

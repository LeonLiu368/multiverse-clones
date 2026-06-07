#!/usr/bin/env bash
# Build (and optionally push) the single slack-service image — the prebuilt backend every task
# pulls. Run when the gateway/seeder/entrypoint or pinned deps change. CI does this on push to main.
#
#   ./build.sh                                                  # -> slack-service:local
#   REGISTRY=ghcr.io/abundant-ai TAG=latest PUSH=1 ./build.sh   # -> ghcr.io/abundant-ai/slack-service:latest (pushed)
set -euo pipefail
cd "$(dirname "$0")"
TAG="${TAG:-local}"
PREFIX=""; [ -n "${REGISTRY:-}" ] && PREFIX="${REGISTRY%/}/"
IMAGE="${PREFIX}slack-service:${TAG}"
echo "building $IMAGE"
docker build --platform linux/amd64 -f Dockerfile.service -t "$IMAGE" .
if [ "${PUSH:-0}" = "1" ]; then
  [ -n "${REGISTRY:-}" ] || { echo "PUSH=1 requires REGISTRY" >&2; exit 1; }
  docker push "$IMAGE"; echo "pushed $IMAGE"
fi
echo "done: $IMAGE"

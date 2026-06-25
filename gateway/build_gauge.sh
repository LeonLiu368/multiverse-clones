#!/usr/bin/env bash
# build_gauge.sh <state.json> <image-tag> [base-image]
set -euo pipefail
STATE="${1:?state.json}"; TAG="${2:?tag}"; BASE="${3:-ghcr.io/abundant-ai/gauge-gateway:empty}"
HERE="$(cd "$(dirname "$0")" && pwd)"; CTX="$(mktemp -d)"; trap 'rm -rf "$CTX"' EXIT
cp "$HERE/gauge.Dockerfile" "$CTX/Dockerfile"; cp "$STATE" "$CTX/state.json"
docker build --platform linux/amd64 --build-arg "BASE=$BASE" -t "$TAG" "$CTX"; echo "built $TAG"

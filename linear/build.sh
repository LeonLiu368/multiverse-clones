#!/usr/bin/env bash
# build.sh <state.json> <image-tag>
set -euo pipefail
STATE="${1:?state.json}"; TAG="${2:?tag}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"; CTX="$(mktemp -d)"; trap 'rm -rf "$CTX"' EXIT
cp -r "$HERE/linear" "$CTX/linear"; cp "$HERE/linear/Dockerfile" "$CTX/Dockerfile"; cp "$STATE" "$CTX/state.json"
docker build --platform linux/amd64 -t "$TAG" "$CTX"; echo "built $TAG"

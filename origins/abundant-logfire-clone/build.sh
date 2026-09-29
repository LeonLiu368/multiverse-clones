#!/usr/bin/env bash
# build.sh <records.json> <image-tag>
set -euo pipefail
RECORDS="${1:?records.json}"; TAG="${2:?tag}"
HERE="$(cd "$(dirname "$0")" && pwd)"; CTX="$(mktemp -d)"; trap 'rm -rf "$CTX"' EXIT
cp -r "$HERE/logfire_clone" "$HERE/Dockerfile" "$CTX/"; cp "$RECORDS" "$CTX/records.json"
docker build --platform linux/amd64 -t "$TAG" "$CTX"; echo "built $TAG"

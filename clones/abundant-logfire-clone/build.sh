#!/usr/bin/env bash
# build.sh — build the logfire image trio locally (the canon: base -> :empty + :prod-v1)
# plus the agent. Mirrors the multi-arch CI publish (see .github/workflows). Local builds
# are single-arch (host); CI publishes linux/amd64,linux/arm64.
#
#   ./build.sh                  # build all four with default ghcr.io/abundant-ai names
#   ./build.sh <registry/ns>    # override the image namespace
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
NS="${1:-ghcr.io/abundant-ai}"

base="$NS/logfire-service:latest"
empty="$NS/logfire-service:empty"
prod="$NS/logfire-service:prod-v1"
agent="$NS/logfire-agent:latest"

echo "== base  $base"
docker build -t "$base"  -f "$HERE/docker/Dockerfile" "$HERE"
echo "== empty $empty"
docker build -t "$empty" -f "$HERE/docker/Dockerfile.empty"  --build-arg BASE="$base" "$HERE"
echo "== prod  $prod (bakes corpus/records.json.gz)"
docker build -t "$prod"  -f "$HERE/docker/Dockerfile.prod-v1" --build-arg BASE="$base" "$HERE"
echo "== agent $agent"
docker build -t "$agent" -f "$HERE/docker/Dockerfile.agent" "$HERE"

echo "built: $base  $empty  $prod  $agent"

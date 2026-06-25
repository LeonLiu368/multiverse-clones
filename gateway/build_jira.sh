#!/usr/bin/env bash
# Bake a spoink Linear/issue state.json into a jira-gateway image.
#   build_jira.sh <state.json> <image-tag> <project-key> [base-image]
set -euo pipefail
STATE="${1:?state.json}"; TAG="${2:?image tag}"; PROJECT="${3:?project key, e.g. ABT}"
BASE="${4:-ghcr.io/abundant-ai/jira-gateway:empty}"
HERE="$(cd "$(dirname "$0")" && pwd)"
CTX="$(mktemp -d)"
trap 'rm -rf "$CTX"' EXIT
cp "$HERE/jira.Dockerfile" "$CTX/Dockerfile"
cp "$STATE" "$CTX/state.json"
docker build --platform linux/amd64 --build-arg "BASE=$BASE" --build-arg "PROJECT=$PROJECT" -t "$TAG" "$CTX"
echo "built $TAG"

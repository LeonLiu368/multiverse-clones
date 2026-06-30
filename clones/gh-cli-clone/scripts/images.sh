#!/usr/bin/env bash
# Build and push the ghc-service gateway image TRIO (canon R2).
#
#   ghc-service            base: Forgejo + gh CLI/MCP + Actions runner, NO DATA
#   ghc-service:empty      == base (boots empty; per-task fixture mounted at /fixture)
#   ghc-service:prod-v1    corpus DB BAKED IN; boots mount-free and serves the corpus
#
# Switching a task between empty and prod-v1 is the image TAG ALONE. Per-task data
# for `:empty` arrives as a BIND MOUNT into the gateway (never COPY'd into a
# per-task image).
#
# Usage:
#   REGISTRY=ghcr.io/abundant-ai scripts/images.sh build     # build all three locally (single-arch)
#   scripts/images.sh push                                   # push all three
#   scripts/images.sh all                                    # build + push
#   scripts/images.sh buildx-multiarch                       # multi-arch build+push (amd64,arm64)
#   scripts/images.sh login
set -euo pipefail

REGISTRY="${REGISTRY:-ghcr.io/abundant-ai}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GW="$ROOT/selfcontained/gateway"
IMAGE="ghc-service"
PLATFORMS="${PLATFORMS:-linux/amd64,linux/arm64}"

# All builds use the repo root as context so `ghclone/` is available; the
# gateway Dockerfiles reference it via selfcontained/gateway/*.

build_base()  { docker build -f "$GW/Dockerfile"          -t "$REGISTRY/$IMAGE:latest" -t "$REGISTRY/$IMAGE:empty" "$ROOT"; }
build_prod()  { docker build -f "$GW/Dockerfile.prod-v1"  --build-arg "BASE=$REGISTRY/$IMAGE:latest" -t "$REGISTRY/$IMAGE:prod-v1" "$ROOT"; }

build() {
  echo ">> building $REGISTRY/$IMAGE {latest,empty}"; build_base
  echo ">> building $REGISTRY/$IMAGE:prod-v1 (baking corpus)"; build_prod
  echo "built trio: $IMAGE:{latest,empty,prod-v1}"
}

push() {
  for t in latest empty prod-v1; do docker push "$REGISTRY/$IMAGE:$t"; done
}

# Multi-arch build+push in one shot (CI uses the equivalent buildx steps).
buildx_multiarch() {
  docker buildx create --use --name ghc-builder >/dev/null 2>&1 || docker buildx use ghc-builder
  echo ">> buildx $PLATFORMS base {latest,empty}"
  docker buildx build --platform "$PLATFORMS" -f "$GW/Dockerfile" \
    -t "$REGISTRY/$IMAGE:latest" -t "$REGISTRY/$IMAGE:empty" --push "$ROOT"
  echo ">> buildx $PLATFORMS prod-v1 (bakes corpus per-arch)"
  docker buildx build --platform "$PLATFORMS" -f "$GW/Dockerfile.prod-v1" \
    --build-arg "BASE=$REGISTRY/$IMAGE:latest" \
    -t "$REGISTRY/$IMAGE:prod-v1" --push "$ROOT"
}

login() {
  cat <<EOF
# 1. token with write:packages:
gh auth refresh -h github.com -s write:packages
# 2. log in to GHCR:
gh auth token | docker login ghcr.io -u <github-username> --password-stdin
EOF
}

case "${1:-build}" in
  build) build ;;
  push) push ;;
  all) build && push ;;
  buildx-multiarch) buildx_multiarch ;;
  login) login ;;
  *) echo "usage: $0 {build|push|all|buildx-multiarch|login} (REGISTRY=$REGISTRY)"; exit 2 ;;
esac

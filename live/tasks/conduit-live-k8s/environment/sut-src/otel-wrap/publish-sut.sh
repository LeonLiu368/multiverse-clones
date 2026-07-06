#!/usr/bin/env bash
# OPTIONAL maintenance helper — NOT part of the task's build/run path.
#
# Rebuilds and republishes the conduit-otel SUT image to the PUBLIC ghcr package
# the manifests reference (ghcr.io/abundant-ai/conduit-otel:latest). The task
# itself never builds the SUT: k3s pulls the published public image at runtime
# (imagePullPolicy: IfNotPresent). Run this only to (re)publish that image.
#
# Recipe = the vendored RealWorld "Conduit" backend
#   nsidnev/fastapi-realworld-example-app @ 029eb7781c60d5f563ee8990a0cbfb79b244538c
# with the OTel auto-instrumentation overlay (this dir's Dockerfile +
# requirements.txt) laid over the app at the repo root. The vendored app source is
# NOT kept in the task dir anymore (the published image carries it) — this script
# re-fetches it from upstream so the build is reproducible from provenance alone.
#
#   ./publish-sut.sh                 # build + push (needs `docker login ghcr.io`)
#   PUSH=0 ./publish-sut.sh          # build only
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

IMAGE="${IMAGE:-ghcr.io/abundant-ai/conduit-otel:latest}"
PLATFORM="${PLATFORM:-linux/arm64}"
UPSTREAM="${UPSTREAM:-https://github.com/nsidnev/fastapi-realworld-example-app}"
COMMIT="${COMMIT:-029eb7781c60d5f563ee8990a0cbfb79b244538c}"

BUILD="$(mktemp -d)"
cleanup() { rm -rf "$BUILD"; }
trap cleanup EXIT

echo "### fetching vendored SUT source ($UPSTREAM @ ${COMMIT:0:7})"
git clone --quiet "$UPSTREAM" "$BUILD/src"
git -C "$BUILD/src" checkout --quiet "$COMMIT"
rm -rf "$BUILD/src/.git"

echo "### overlaying the OTel wrapper (Dockerfile + requirements.txt)"
cp "$HERE/Dockerfile" "$HERE/requirements.txt" "$BUILD/src/"

echo "### building $IMAGE ($PLATFORM, --provenance=false -> single-arch manifest)"
docker build --provenance=false --platform "$PLATFORM" -t "$IMAGE" "$BUILD/src"

if [ "${PUSH:-1}" = "1" ]; then
  echo "### pushing $IMAGE (requires: docker login ghcr.io)"
  docker push "$IMAGE"
  echo "### pushed. confirm:"
  docker manifest inspect "$IMAGE" | head -6
else
  echo "### PUSH=0 — built only, not pushed"
fi

#!/usr/bin/env bash
# Produce the airgap image tars the k3s image bakes into
# /var/lib/rancher/k3s/agent/images/ (imported into k3s containerd at boot).
#
# Run this BEFORE `docker compose build k3s`. It:
#   1. builds the conduit-otel SUT image (vendored app/ + otel-wrap overlay), and
#   2. `docker save`s the 4 workload images (postgres, otel-collector, the
#      private logfire-service, conduit-otel) into ./airgap/*.tar.
#
# Why bake instead of let k3s pull: k3s uses containerd, not docker, so Oddish's
# `--registry-login` (a docker login) does NOT authenticate k3s pulls. Baking is
# hermetic — no runtime registry auth for public OR private images.
#
# On Oddish/CI the private base images (logfire-service; and whatever registry the
# SUT is pushed to) are already pulled by Harbor's --registry-login before build,
# so `docker save` finds them locally exactly as it does here.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENVDIR="$(cd "$HERE/.." && pwd)"
AIRGAP="$HERE/airgap"
PLATFORM="${PLATFORM:-linux/arm64}"   # match the cluster node arch

LOGFIRE_IMAGE="${LOGFIRE_IMAGE:-ghcr.io/abundant-ai/logfire-service:latest}"
POSTGRES_IMAGE="postgres:16"
OTELCOL_IMAGE="otel/opentelemetry-collector-contrib:0.116.1"
SUT_IMAGE="conduit-otel:latest"

mkdir -p "$AIRGAP"

echo "### assembling + building the conduit-otel SUT image ($PLATFORM)"
BUILD="$(mktemp -d)"
cp -R "$ENVDIR/sut-src/app/." "$BUILD/"
cp "$ENVDIR/sut-src/otel-wrap/Dockerfile" \
   "$ENVDIR/sut-src/otel-wrap/requirements.txt" "$BUILD/"
# --provenance=false: a single-arch docker-manifest image (no attestation manifest
# list), which k3s's airgap importer handles cleanly.
docker build --provenance=false --platform "$PLATFORM" -t "$SUT_IMAGE" "$BUILD"
rm -rf "$BUILD"

echo "### ensuring public images are present locally ($PLATFORM)"
for img in "$POSTGRES_IMAGE" "$OTELCOL_IMAGE" "$LOGFIRE_IMAGE"; do
  docker image inspect "$img" >/dev/null 2>&1 || docker pull --platform "$PLATFORM" "$img"
done

echo "### docker save -> airgap tars"
docker save "$POSTGRES_IMAGE" -o "$AIRGAP/postgres.tar"
docker save "$OTELCOL_IMAGE"  -o "$AIRGAP/otel-collector.tar"
docker save "$LOGFIRE_IMAGE"  -o "$AIRGAP/logfire.tar"
docker save "$SUT_IMAGE"      -o "$AIRGAP/conduit-otel.tar"

echo "### airgap tars ready:"
ls -lh "$AIRGAP"/*.tar

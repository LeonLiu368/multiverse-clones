#!/usr/bin/env bash
# Build the aws-clone gateway IMAGE TRIO locally:
#   aws-clone-service:base    — base API + tools, no data
#   aws-clone-service:prod-v1 — corpus state.json BAKED IN (boots mount-free)
#   aws-clone-service:empty   — base API, no data (per-task fixture mounted in)
#
# This lets the Harbor task (environment/docker-compose.yaml) and the example
# composes resolve the gateway with NO registry creds (R1.5): the service carries
# both `build:` and `image:`, so `docker compose build` tags the pullable name
# locally even when the GHCR package is private/unpublished.
set -euo pipefail
cd "$(dirname "$0")"

BASE_TAG="${BASE_TAG:-aws-clone-service:base}"

echo ">> building ${BASE_TAG}"
docker build -f Dockerfile.service -t "${BASE_TAG}" .

echo ">> building aws-clone-service:prod-v1 (baked corpus)"
docker build -f Dockerfile.prod-v1 --build-arg "BASE=${BASE_TAG}" -t aws-clone-service:prod-v1 .

echo ">> building aws-clone-service:empty (mount target)"
docker build -f Dockerfile.empty --build-arg "BASE=${BASE_TAG}" -t aws-clone-service:empty .

echo ">> done: aws-clone-service:{base,prod-v1,empty}"

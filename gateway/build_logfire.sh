#!/usr/bin/env bash
# Bake a spoink-captured Logfire records.json into a logfire-service image.
#   build_logfire.sh <records.json> <image-tag> [base-image]
#
# The multiverse abundant-logfire-clone bakes a corpus by COPYing corpus/records.json.gz
# and setting $LOGFIRE_BAKED (docker/Dockerfile.prod-v1); the entrypoint then serves it and
# ignores any mount. We reuse that canonical Dockerfile but supply OUR records as the corpus,
# so spoink stays in lockstep with the clone instead of duplicating its bake logic.
set -euo pipefail
RECORDS="${1:?records.json}"; TAG="${2:?image tag}"
BASE="${3:-ghcr.io/abundant-ai/logfire-service:latest}"
CLONE="${LOGFIRE_CLONE_DIR:-$HOME/projects/multiverse-clones/clones/abundant-logfire-clone}"
DF="$CLONE/docker/Dockerfile.prod-v1"
[ -f "$DF" ] || { echo "logfire clone Dockerfile.prod-v1 not found at $DF (set LOGFIRE_CLONE_DIR)" >&2; exit 1; }

CTX="$(mktemp -d)"; trap 'rm -rf "$CTX"' EXIT
mkdir -p "$CTX/corpus"
gzip -c "$RECORDS" > "$CTX/corpus/records.json.gz"
cp "$DF" "$CTX/Dockerfile"
docker build --build-arg "BASE=$BASE" -t "$TAG" "$CTX"
echo "built $TAG"

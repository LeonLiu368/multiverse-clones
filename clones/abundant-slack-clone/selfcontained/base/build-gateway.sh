#!/usr/bin/env bash
# Build a `slack-gateway:<dataset>` sidecar image = the SQLite gateway + a dataset's pre-built DB
# (from slack-seed:<dataset>). This is what a task's `slack` sidecar pulls.
#
#   DATASET=eng-2021q1 ./build-gateway.sh                                  # local (-> :local load)
#   REGISTRY=ghcr.io/abundant-ai PUSH=1 PLATFORM=linux/amd64 \
#     DATASET=eng-2021q1 ./build-gateway.sh                               # build + push
#
# SEED defaults to ghcr.io/abundant-ai/slack-seed:<dataset>; override SEED to point elsewhere.
set -euo pipefail
cd "$(dirname "$0")"
: "${DATASET:?set DATASET (e.g. eng-2021q1 or full)}"
REG="${REGISTRY:+${REGISTRY%/}/}"
IMAGE="${REG}slack-gateway:${DATASET}"
SEED="${SEED:-ghcr.io/abundant-ai/slack-seed:${DATASET}}"
SVC="${SLACK_SERVICE:-ghcr.io/abundant-ai/slack-service:slack-mcp-oss}"

ARGS=(buildx build --build-arg "SEED=${SEED}" --build-arg "SLACK_SERVICE=${SVC}"
      -f Dockerfile.gateway -t "$IMAGE")
[ -n "${PLATFORM:-}" ] && ARGS+=(--platform "$PLATFORM")
if [ "${PUSH:-0}" = "1" ]; then ARGS+=(--push); else ARGS+=(--load); fi

echo "building gateway sidecar $IMAGE (seed=$SEED)"
docker "${ARGS[@]}" .
echo "done: $IMAGE"

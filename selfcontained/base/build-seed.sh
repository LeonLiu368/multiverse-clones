#!/usr/bin/env bash
# Build a `slack-seed` image with a PRE-BUILT SQLite DB from a real Slack export directory.
# The export does NOT need to live in this repo — point EXPORT_DIR at it on disk.
#
#   EXPORT_DIR=/path/to/slack-export DATASET=eng-2021q1 ./build-seed.sh                 # local (-> :local load)
#   REGISTRY=ghcr.io/abundant-ai PUSH=1 PLATFORM=linux/amd64 \
#     EXPORT_DIR=/path/to/slack-export DATASET=eng-2021q1 ./build-seed.sh               # build + push amd64
#
# Then a task pulls the ready DB at build time:
#   FROM ghcr.io/abundant-ai/slack-service:slack-mcp-oss
#   COPY --from=ghcr.io/abundant-ai/slack-seed:eng-2021q1 /slack.prebuilt.db /opt/slack.prebuilt.db
set -euo pipefail
cd "$(dirname "$0")"
: "${EXPORT_DIR:?set EXPORT_DIR to a Slack export directory}"
: "${DATASET:?set DATASET (the image tag, e.g. eng-2021q1)}"
[ -d "$EXPORT_DIR" ] || { echo "EXPORT_DIR not a directory: $EXPORT_DIR" >&2; exit 1; }

REG="${REGISTRY:+${REGISTRY%/}/}"
IMAGE="${REG}slack-seed:${DATASET}"
SVC="${SLACK_SERVICE:-ghcr.io/abundant-ai/slack-service:slack-mcp-oss}"

ARGS=(buildx build --build-context "export=${EXPORT_DIR}" --build-arg "SLACK_SERVICE=${SVC}"
      -f Dockerfile.seed -t "$IMAGE")
[ -n "${PLATFORM:-}" ] && ARGS+=(--platform "$PLATFORM")
if [ "${PUSH:-0}" = "1" ]; then ARGS+=(--push); else ARGS+=(--load); fi

echo "building seed image $IMAGE from $EXPORT_DIR"
docker "${ARGS[@]}" .
echo "done: $IMAGE"

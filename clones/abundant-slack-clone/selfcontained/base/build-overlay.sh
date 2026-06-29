#!/usr/bin/env bash
# Build a per-task `slack-gateway:<task>` sidecar = the shared prod gateway + a task's tiny overlay.
# The prod base layers are shared/cached; only the small overlay layer differs per task.
#
#   OVERLAY_DIR=/path/to/task/environment/data TAG=arrival-time ./build-overlay.sh                # local
#   REGISTRY=ghcr.io/abundant-ai PUSH=1 PLATFORM=linux/amd64 \
#     OVERLAY_DIR=/path/to/task/environment/data TAG=arrival-time ./build-overlay.sh              # push
#
# OVERLAY_DIR must contain an `overlay/` subdir (a Slack export shape). PROD defaults to prod-v1.
set -euo pipefail
cd "$(dirname "$0")"
: "${OVERLAY_DIR:?set OVERLAY_DIR (dir containing overlay/)}"
: "${TAG:?set TAG (the per-task image tag, e.g. arrival-time)}"
[ -d "$OVERLAY_DIR/overlay" ] || { echo "no overlay/ under $OVERLAY_DIR" >&2; exit 1; }
REG="${REGISTRY:+${REGISTRY%/}/}"
IMAGE="${REG}slack-gateway:${TAG}"
PROD="${PROD:-ghcr.io/abundant-ai/slack-gateway:prod-v1}"
ARGS=(buildx build --build-arg "PROD=${PROD}" -f Dockerfile.overlay -t "$IMAGE")
[ -n "${PLATFORM:-}" ] && ARGS+=(--platform "$PLATFORM")
if [ "${PUSH:-0}" = "1" ]; then ARGS+=(--push); else ARGS+=(--load); fi
echo "building overlay sidecar $IMAGE (prod=$PROD)"
docker "${ARGS[@]}" "$OVERLAY_DIR"
echo "done: $IMAGE"

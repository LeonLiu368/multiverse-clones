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
: "${DATASET:?set DATASET (the image tag, e.g. eng-2021q1)}"

REG="${REGISTRY:+${REGISTRY%/}/}"
IMAGE="${REG}slack-seed:${DATASET}"
SVC="${SLACK_SERVICE:-ghcr.io/abundant-ai/slack-service:slack-mcp-oss}"

# Two modes:
#   DB_FILE=/path/to/slack.db   -> bake an ALREADY-BUILT DB (best for LARGE exports: build it once
#                                  natively with import_export.py, then bake fast/multi-arch here).
#   EXPORT_DIR=/path/to/export  -> import the raw export at build time (good for small datasets).
if [ -n "${DB_FILE:-}" ]; then
  [ -f "$DB_FILE" ] || { echo "DB_FILE not found: $DB_FILE" >&2; exit 1; }
  CTX="$(mktemp -d)"; cp "$DB_FILE" "$CTX/slack.prebuilt.db"
  printf 'FROM scratch\nCOPY slack.prebuilt.db /slack.prebuilt.db\n' > "$CTX/Dockerfile"
  ARGS=(buildx build -t "$IMAGE")
  [ -n "${PLATFORM:-}" ] && ARGS+=(--platform "$PLATFORM")
  if [ "${PUSH:-0}" = "1" ]; then ARGS+=(--push); else ARGS+=(--load); fi
  echo "baking seed image $IMAGE from prebuilt DB $DB_FILE"
  docker "${ARGS[@]}" "$CTX"; rm -rf "$CTX"
else
  : "${EXPORT_DIR:?set EXPORT_DIR (a Slack export dir) or DB_FILE (a prebuilt slack.db)}"
  [ -d "$EXPORT_DIR" ] || { echo "EXPORT_DIR not a directory: $EXPORT_DIR" >&2; exit 1; }
  ARGS=(buildx build --build-context "export=${EXPORT_DIR}" --build-arg "SLACK_SERVICE=${SVC}"
        -f Dockerfile.seed -t "$IMAGE")
  [ -n "${PLATFORM:-}" ] && ARGS+=(--platform "$PLATFORM")
  if [ "${PUSH:-0}" = "1" ]; then ARGS+=(--push); else ARGS+=(--load); fi
  echo "building seed image $IMAGE from export $EXPORT_DIR"
  docker "${ARGS[@]}" .
fi
echo "done: $IMAGE"

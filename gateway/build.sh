#!/usr/bin/env bash
# Build a slack-gateway image with a spoink export baked in.
#   build.sh <export-dir> <image-tag> [base-image]
# The deployed gateway importer reads channels.json only, so we fold private
# (groups.json) / mpim / dm channel metadata into channels.json first.
set -euo pipefail
EXPORT_DIR="${1:?export dir}"; TAG="${2:?image tag}"
BASE="${3:-ghcr.io/abundant-ai/slack-gateway:empty}"
HERE="$(cd "$(dirname "$0")" && pwd)"
SLACK_CLONE="${SLACK_CLONE_DIR:-$HOME/projects/multiverse-clones/clones/abundant-slack-clone}/selfcontained/base"
CTX="$(mktemp -d)"
trap 'rm -rf "$CTX"' EXIT

# ensure the empty gateway base exists. it isn't published to GHCR, so if it's not already
# local (or pullable) build it from the slack clone's Dockerfile.empty (on top of slack-service).
if ! docker image inspect "$BASE" >/dev/null 2>&1 && ! docker pull "$BASE" >/dev/null 2>&1; then
  [ -f "$SLACK_CLONE/Dockerfile.empty" ] || {
    echo "base $BASE is unavailable and the slack clone isn't at $SLACK_CLONE (set SLACK_CLONE_DIR)" >&2; exit 1; }
  echo ">> $BASE not available — building it from $SLACK_CLONE/Dockerfile.empty"
  docker build --platform linux/amd64 -f "$SLACK_CLONE/Dockerfile.empty" -t "$BASE" "$SLACK_CLONE"
fi

cp "$HERE/Dockerfile" "$CTX/Dockerfile"
cp -a "$EXPORT_DIR" "$CTX/export"

# fold all channel-metadata files into channels.json (the only one the importer reads)
python3 - "$CTX/export" <<'PY'
import json, os, sys
d = sys.argv[1]
merged, seen = [], set()
for f in ("channels.json", "groups.json", "mpims.json", "dms.json"):
    p = os.path.join(d, f)
    if os.path.exists(p):
        for c in json.load(open(p)):
            key = c.get("id") or c.get("name")
            if key not in seen:
                merged.append(c); seen.add(key)
json.dump(merged, open(os.path.join(d, "channels.json"), "w"))
print(f"channels.json: {len(merged)} channels")
PY

docker build --platform linux/amd64 --build-arg "BASE=$BASE" -t "$TAG" "$CTX"
echo "built $TAG"

#!/usr/bin/env bash
# Bake a spoink Slack export into a slack-gateway image using the CLONE'S VERIFIED pipeline:
#   build-seed.sh  (export -> prebuilt SQLite DB, on slack-service:slack-mcp-oss)
#   build-gateway.sh (gateway + that seed -> slack-gateway:<tag>)
# This is the path verified in multiverse-clones — it uses the PUBLISHED slack-service base, not the
# unpublished slack-gateway:empty. Override the clone location with $SLACK_CLONE_DIR.
#   build.sh <export-dir> <image-ref>        e.g. ghcr.io/abundant-ai/slack-gateway:june-snap
set -euo pipefail
EXPORT_DIR="${1:?export dir}"; IMAGE="${2:?image ref}"
CLONE="${SLACK_CLONE_DIR:-$HOME/projects/multiverse-clones/clones/abundant-slack-clone}/selfcontained/base"
[ -f "$CLONE/build-seed.sh" ] && [ -f "$CLONE/build-gateway.sh" ] || {
  echo "slack clone build scripts not found under $CLONE (set SLACK_CLONE_DIR)" >&2; exit 1; }

# ghcr.io/<ns>/slack-gateway:<TAG>  ->  REGISTRY=ghcr.io/<ns>  DATASET=<TAG>
TAG="${IMAGE##*:}"; REPO="${IMAGE%:*}"; REGISTRY="${REPO%/*}"

FOLDED="$(mktemp -d)"; trap 'rm -rf "$FOLDED"' EXIT
cp -a "$EXPORT_DIR/." "$FOLDED/"
# the clone importer reads channels.json only — fold private/mpim/dm metadata into it
python3 - "$FOLDED" <<'PY'
import json, os, sys
d = sys.argv[1]; merged, seen = [], set()
for f in ("channels.json", "groups.json", "mpims.json", "dms.json"):
    p = os.path.join(d, f)
    if os.path.exists(p):
        for c in json.load(open(p)):
            k = c.get("id") or c.get("name")
            if k not in seen:
                merged.append(c); seen.add(k)
json.dump(merged, open(os.path.join(d, "channels.json"), "w"))
print(f"channels.json: {len(merged)} channels")
PY

export DATASET="$TAG" REGISTRY="$REGISTRY" PLATFORM="${PLATFORM:-linux/amd64}"
echo ">> [1/2] build-seed ($DATASET) from the spoink export"
EXPORT_DIR="$FOLDED" bash "$CLONE/build-seed.sh"
echo ">> [2/2] build-gateway ($DATASET) -> $IMAGE"
bash "$CLONE/build-gateway.sh"
echo "built $IMAGE"

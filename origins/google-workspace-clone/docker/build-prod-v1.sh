#!/usr/bin/env bash
# Build + push the gworkspace-service:empty / :prod-v1 controlled-difficulty pair.
#
#   :empty    — the data-free base (docker/Dockerfile). Seeds the per-task needle from
#               a mounted fixture; on its own it serves nothing. Same bits as :latest.
#   :prod-v1  — FROM :empty with a deterministic Drive corpus baked in (the needle +
#               adversarial decoys + filler). Ignores any per-task mount; serves the
#               full corpus. A task flips empty<->prod-v1 by the image tag alone.
#
# Usage:  docker/build-prod-v1.sh [--push]   (default: local --load, amd64 only)
set -euo pipefail
cd "$(dirname "$0")/.."

REG="${REG:-ghcr.io/abundant-ai}"
PY="${PY:-python3}"
PLATFORMS="${PLATFORMS:-linux/amd64,linux/arm64}"
MODE="--load"; PLAT="linux/amd64"
[ "${1:-}" = "--push" ] && { MODE="--push"; PLAT="$PLATFORMS"; }

echo "=== regenerate deterministic corpus -> docker/gws_corpus.db ==="
$PY -m gwsclone.cli.main seed gen-corpus --out docker/gws_corpus.db >/dev/null
$PY - <<'PY'
import sqlite3; n=sqlite3.connect("docker/gws_corpus.db").execute("select count(*) from drive_files").fetchone()[0]
print(f"  baked corpus: {n} drive files")
PY

echo "=== build :empty (data-free base) ==="
docker buildx build --platform "$PLAT" -f docker/Dockerfile -t "$REG/gworkspace-service:empty" $MODE .

echo "=== build :prod-v1 (corpus baked) ==="
docker buildx build --platform "$PLAT" -f docker/Dockerfile.prod-v1 \
  --build-arg "BASE=$REG/gworkspace-service:empty" \
  -t "$REG/gworkspace-service:prod-v1" $MODE docker

echo "=== done ($MODE) ==="

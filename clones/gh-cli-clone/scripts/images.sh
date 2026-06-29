#!/usr/bin/env bash
# Build and push the public gh-cli-clone service image.
#
# One reusable image, matching the Slack/TicketVector task-pack pattern:
#   ghc-service  Forgejo + gh-compatible CLI + Actions runner support
#
# Usage:
#   REGISTRY=ghcr.io/abundant-ai TAG=latest scripts/images.sh build
#   scripts/images.sh push
#   scripts/images.sh all
#   scripts/images.sh pull
#   scripts/images.sh login
#
# Tasks use ghc-service as the GitHub sidecar and copy /usr/local/bin/gh from it
# into the agent's thin main image.
set -euo pipefail

REGISTRY="${REGISTRY:-ghcr.io/abundant-ai}"
TAG="${TAG:-latest}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ISO="$ROOT/selfcontained/isolated"
IMAGE="ghc-service"

_ctx() {
  CTX="$(mktemp -d)"
  cp -r "$ROOT/ghclone" "$CTX/ghclone"
  find "$CTX/ghclone" -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
  cp "$ISO/Dockerfile.forge-actions" "$CTX/Dockerfile"
  cp "$ISO/forge-entrypoint-actions.sh" "$CTX/forge-entrypoint.sh"
  printf '#!/usr/bin/env bash\n# no-op base seed - tasks override this file.\nexit 0\n' > "$CTX/seed.sh"
}

build() {
  _ctx
  echo ">> building $REGISTRY/$IMAGE:$TAG"
  docker build -t "$REGISTRY/$IMAGE:$TAG" -f "$CTX/Dockerfile" "$CTX"
  rm -rf "$CTX"
  echo "built: $REGISTRY/$IMAGE:$TAG"
}

push() { docker push "$REGISTRY/$IMAGE:$TAG"; }
pull() { docker pull "$REGISTRY/$IMAGE:$TAG"; }

login() {
  cat <<EOF
# 1. get a token with write:packages (one of):
gh auth refresh -h github.com -s write:packages
# ...or create a classic PAT with write:packages at github.com/settings/tokens
# 2. log in to GHCR:
gh auth token | docker login ghcr.io -u <github-username> --password-stdin
EOF
}

# ---- registry-free sharing (docker save/load via tarballs + GitHub Releases) ----
OUT="${OUT:-./image-dist}"
SHARE_REPO="${SHARE_REPO:-abundant-ai/gh-cli-clone}"

save() {
  mkdir -p "$OUT"
  echo ">> saving $REGISTRY/$IMAGE:$TAG -> $OUT/$IMAGE-$TAG.tar.gz"
  docker save "$REGISTRY/$IMAGE:$TAG" | gzip > "$OUT/$IMAGE-$TAG.tar.gz"
  ls -lh "$OUT"/*.tar.gz
}

load() {
  for f in "$OUT"/*.tar.gz; do echo ">> loading $f"; gzip -dc "$f" | docker load; done
}

release() {
  local tag="${1:-images-$TAG}"
  save
  if gh release view "$tag" -R "$SHARE_REPO" >/dev/null 2>&1; then
    gh release upload "$tag" "$OUT"/*.tar.gz -R "$SHARE_REPO" --clobber
  else
    gh release create "$tag" "$OUT"/*.tar.gz -R "$SHARE_REPO" \
      -t "ghc service image ($tag)" \
      -n "Docker image for gh-cli-clone. Install: \`gh release download $tag -R $SHARE_REPO -p '*.tar.gz' && for f in *.tar.gz; do docker load < \$f; done\`"
  fi
  echo "shared via release '$tag' on $SHARE_REPO (no registry needed)"
}

install() {
  local tag="${1:-images-$TAG}"
  mkdir -p "$OUT"
  gh release download "$tag" -R "$SHARE_REPO" -p '*.tar.gz' -D "$OUT" --clobber
  load
}

case "${1:-build}" in
  build) build ;;
  push) push ;;
  pull) pull ;;
  all) build && push ;;
  login) login ;;
  save) save ;;
  load) load ;;
  release) release "${2:-}" ;;
  install) install "${2:-}" ;;
  *) echo "usage: $0 {build|push|pull|all|login|save|load|release|install} (REGISTRY=$REGISTRY TAG=$TAG)"; exit 2 ;;
esac

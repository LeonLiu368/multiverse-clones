#!/usr/bin/env bash
# Register + start a Forgejo act_runner so Actions workflows actually EXECUTE.
# Idempotent-ish: recreates the runner each call. Requires the forge up + a token.
#
#   GHC_HOST=http://localhost:3300 GHC_TOKEN=$(cat ghc-token.txt) bash scripts/start-runner.sh
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
export GHC_TOKEN="${GHC_TOKEN:-$(cat "$HERE/ghc-token.txt")}"
GHC="$HERE/.venv/bin/ghc"
IMAGE="code.forgejo.org/forgejo/runner:6"

NET=$(docker inspect ghc-forgejo -f '{{range $k,$v := .NetworkSettings.Networks}}{{$k}}{{end}}')
TOKEN=$("$GHC" api admin/runners/registration-token | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')

echo "==> registering runner on network $NET"
docker rm -f ghc-runner >/dev/null 2>&1 || true
docker volume rm ghc-runner-data >/dev/null 2>&1 || true
docker run --rm -v ghc-runner-data:/data --network "$NET" "$IMAGE" \
  forgejo-runner register --no-interactive --instance http://forgejo:3000 \
  --token "$TOKEN" --name ghc-runner --labels docker:docker://node:20-bookworm >/dev/null 2>&1

# Put job containers on the forge network so checkout + artifact upload can reach
# the forge (the artifact action posts to ROOT_URL = host.docker.internal:3300).
echo "==> configuring runner job network = $NET"
CFG=$(mktemp)
docker run --rm "$IMAGE" forgejo-runner generate-config 2>/dev/null \
  | sed "s|  network: \"\"|  network: \"$NET\"|" > "$CFG"
docker run --rm -v ghc-runner-data:/data -v "$CFG":/cfg.yaml "$IMAGE" cp /cfg.yaml /data/config.yaml
rm -f "$CFG"

echo "==> starting runner daemon (root, with docker.sock)"
docker run -d --name ghc-runner --network "$NET" --user root \
  -v ghc-runner-data:/data \
  -v /var/run/docker.sock:/var/run/docker.sock \
  "$IMAGE" forgejo-runner daemon --config /data/config.yaml >/dev/null

sleep 3
docker ps --filter name=ghc-runner --format '  runner: {{.Status}}'
echo "Actions will now execute. Push a .forgejo/workflows/*.yml with 'runs-on: docker'."

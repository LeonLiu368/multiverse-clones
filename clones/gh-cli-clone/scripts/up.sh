#!/usr/bin/env bash
# Bring up the WHOLE offline stack in one command:
#   1. Forgejo (forge)        2. admin + API token        3. act_runner (so Actions run)
#
#   bash scripts/up.sh
# Then:  export GHC_HOST=http://localhost:3300 GHC_TOKEN=$(cat ghc-token.txt)
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
cd "$HERE"

echo "==> 1/3 forge"
docker compose -f docker/docker-compose.yml up -d forgejo

echo "==> 2/3 admin + token"
bash scripts/bootstrap.sh >/dev/null
export GHC_HOST=http://localhost:3300
export GHC_TOKEN="$(cat ghc-token.txt)"
echo "    token -> ghc-token.txt"

echo "==> 3/3 act_runner (workflow execution)"
bash scripts/start-runner.sh

echo
echo "stack up. Forgejo http://localhost:3300 | runner registered | Actions will execute."
echo "  export GHC_HOST=http://localhost:3300 GHC_TOKEN=\$(cat ghc-token.txt)"

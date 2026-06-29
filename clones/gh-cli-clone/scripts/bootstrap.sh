#!/usr/bin/env bash
# Bootstrap the offline forge: create an admin user and an API token, then
# write the token to ghc-token.txt + export it for ghc. Idempotent-ish:
# re-running creates a fresh token (old ones stay valid until revoked).
set -euo pipefail

CT=ghc-forgejo
ADMIN_USER="${GHC_ADMIN_USER:-ghc-admin}"
ADMIN_PASS="${GHC_ADMIN_PASS:-ghc-admin-pw-0}"
ADMIN_EMAIL="${GHC_ADMIN_EMAIL:-ghc-admin@local}"
TOKEN_NAME="${GHC_TOKEN_NAME:-ghc-cli}"
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> waiting for Forgejo to be healthy..."
for i in $(seq 1 60); do
  if curl -fsS http://localhost:3300/api/healthz >/dev/null 2>&1; then break; fi
  sleep 2
done

echo "==> ensuring admin user '$ADMIN_USER' exists"
docker exec -u git "$CT" forgejo admin user create \
  --admin --username "$ADMIN_USER" --password "$ADMIN_PASS" \
  --email "$ADMIN_EMAIL" --must-change-password=false 2>/dev/null \
  || echo "   (user already exists, continuing)"

echo "==> generating API token '$TOKEN_NAME' (all scopes)"
TOKEN=$(docker exec -u git "$CT" forgejo admin user generate-access-token \
  --username "$ADMIN_USER" --token-name "$TOKEN_NAME-$RANDOM" \
  --scopes "all" --raw)

echo "$TOKEN" > "$ROOT_DIR/ghc-token.txt"
echo "==> wrote token to ghc-token.txt"
echo
echo "Configure ghc to use it:"
echo "  export GHC_HOST=http://localhost:3300"
echo "  export GHC_TOKEN=\$(cat ghc-token.txt)"
echo "  ghc auth status"

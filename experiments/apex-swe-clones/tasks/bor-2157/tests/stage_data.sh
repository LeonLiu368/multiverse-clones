#!/bin/bash
set -uo pipefail
cd /app/repo || exit 0
git config --global --add safe.directory /app/repo 2>/dev/null || true
for f in eth/peer_test.go; do
  git checkout -- "$f" 2>/dev/null || true
done
mkdir -p /tmp/verifier-scratch && chmod 0700 /tmp/verifier-scratch
exit 0

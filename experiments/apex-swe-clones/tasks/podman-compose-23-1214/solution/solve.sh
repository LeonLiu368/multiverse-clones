#!/bin/bash
set -euo pipefail
cd /app/repo
git config --global --add safe.directory /app/repo 2>/dev/null || true
git apply /solution/golden.patch || patch -p1 < /solution/golden.patch
echo "applied golden.patch for podman-compose-23-1214"

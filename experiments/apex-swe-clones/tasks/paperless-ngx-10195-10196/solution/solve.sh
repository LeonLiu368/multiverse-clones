#!/bin/bash
# Oracle: apply the golden product-code fix to /app/repo.
set -euo pipefail
cd /app/repo
git config --global --add safe.directory /app/repo 2>/dev/null || true
git apply /solution/golden.patch || patch -p1 < /solution/golden.patch
echo "applied golden.patch for paperless-ngx-10195-10196"

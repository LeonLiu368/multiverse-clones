#!/usr/bin/env bash
set -euo pipefail
cd /app/repo
git config --global --add safe.directory /app/repo 2>/dev/null || true
git checkout -- "params/config_test.go" 2>/dev/null || true
git apply --whitespace=nowarn /tests/test.patch 2>/dev/null || patch -p1 < /tests/test.patch

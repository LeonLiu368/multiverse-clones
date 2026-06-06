#!/usr/bin/env bash
# Oracle: #deploys was archived; unarchive (restore) it.
set -euo pipefail
mmctl channel unarchive test-demo:deploys
echo "oracle: unarchived #deploys"

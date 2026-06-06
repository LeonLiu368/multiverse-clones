#!/usr/bin/env bash
# Oracle: #deploys was archived; restore it through the `slack` tool.
set -euo pipefail
slack conversations.unarchive deploys
echo "oracle: unarchived #deploys via slack"

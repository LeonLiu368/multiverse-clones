#!/usr/bin/env bash
# Oracle: carol was deactivated; reactivate her through the `slack` tool.
set -euo pipefail
slack admin.users.setActive carol true
echo "oracle: reactivated carol via slack"

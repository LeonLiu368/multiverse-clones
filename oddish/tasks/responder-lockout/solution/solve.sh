#!/usr/bin/env bash
# Oracle: carol was deactivated; reactivate her.
set -euo pipefail
mmctl user activate carol
echo "oracle: reactivated carol"

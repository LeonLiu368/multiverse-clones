#!/usr/bin/env bash
# Oracle: file sharing was disabled workspace-wide; re-enable it through the `slack` tool.
set -euo pipefail
slack admin.setFileSharing true
echo "oracle: re-enabled file sharing via slack"

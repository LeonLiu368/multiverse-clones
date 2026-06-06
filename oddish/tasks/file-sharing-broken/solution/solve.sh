#!/usr/bin/env bash
# Oracle: file attachments were disabled server-wide; re-enable them.
set -euo pipefail
mmctl config set FileSettings.EnableFileAttachments true
echo "oracle: re-enabled file attachments"

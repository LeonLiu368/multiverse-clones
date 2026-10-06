#!/usr/bin/env bash
set -euo pipefail
# (agent recovers via: figma-cli search "$FIGMA_FILE_KEY" "Date and time - Pickers" -> node 5442:1885
#  then figma-cli node "$FIGMA_FILE_KEY" 5442:1885 -> the variant names)
cat > /app/ios_components/comp.py <<'PY'
"""The date & time picker styles defined in the design."""
from __future__ import annotations


def date_picker_styles() -> list[str]:
    return ["Compact", "Inline"]
PY
echo "oracle: wrote date & time picker styles"

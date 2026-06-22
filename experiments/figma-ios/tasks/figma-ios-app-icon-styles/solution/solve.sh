#!/usr/bin/env bash
set -euo pipefail
# (agent recovers via: figma-cli search "$FIGMA_FILE_KEY" "App Icon/iPhone" -> node 2402:17543
#  then figma-cli node "$FIGMA_FILE_KEY" 2402:17543 -> the variant names)
cat > /app/ios_components/comp.py <<'PY'
"""The App Icon styles defined in the design."""
from __future__ import annotations


def app_icon_styles() -> list[str]:
    return ["Custom", "System"]
PY
echo "oracle: wrote App Icon styles"

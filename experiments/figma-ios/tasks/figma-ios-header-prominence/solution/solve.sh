#!/usr/bin/env bash
set -euo pipefail
# (agent recovers via: figma-cli search "$FIGMA_FILE_KEY" "Header" -> node 517:38042
#  then figma-cli node "$FIGMA_FILE_KEY" 517:38042 -> the variant names)
cat > /app/ios_components/comp.py <<'PY'
"""The Header prominence levels defined in the design."""
from __future__ import annotations


def header_prominence_levels() -> list[str]:
    return ["Extra Prominent", "Nested", "Prominent"]
PY
echo "oracle: wrote Header prominence levels"

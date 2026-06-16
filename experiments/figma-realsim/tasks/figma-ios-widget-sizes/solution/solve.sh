#!/usr/bin/env bash
# Oracle: read the "Home Screen Widgets" component set from the Figma design and
# return its size variants.
# (An agent recovers this with:
#    figma-cli search "$FIGMA_FILE_KEY" "Home Screen Widgets"   -> node 775:13152
#    figma-cli node "$FIGMA_FILE_KEY" 775:13152                 -> children Size=Large/Medium/Small )
set -euo pipefail
cat > /app/ios_widgets/widgets.py <<'PY'
"""The Home Screen Widget sizes offered by the iOS design kit."""

from __future__ import annotations


def home_screen_widget_sizes() -> list[str]:
    return ["Large", "Medium", "Small"]
PY
echo "oracle: wrote widget sizes"

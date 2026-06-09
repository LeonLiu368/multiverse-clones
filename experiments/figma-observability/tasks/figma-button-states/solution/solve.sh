#!/usr/bin/env bash
# Oracle: recover the finalized Button spec from the Figma file (node tree +
# comment thread + Primary/600 style-token resolution), write it into the
# codebase, and post the required completion comment on the Button node.
set -euo pipefail
KEY="${FIGMA_FILE_KEY:-BtnStatesSpecFile0001x}"
export FIGMA_API_URL="${FIGMA_API_URL:-http://figma:3000}"

cat > /app/button_states/states.py <<'PY'
"""Button design-spec values — finalized to match the Figma design."""

from __future__ import annotations


def button_states_spec() -> dict:
    return {
        "label": "Place order",      # comment 7 overrides the stale node text "Buy now"
        "height": 48,                # node 2:1 absoluteBoundingBox.height (only in the node tree)
        "padding_x": 20,             # node 2:1 + final comment 5 (decoy: v1 implied via h44)
        "radius": 10,                # node 2:1 + final comment 5 (decoys: 8 in c1, 12 in c3)
        "default_bg": "#2D6CDF",     # Primary/500 — node fill / comment 2 / styles
        "hover_bg": "#1B4AA8",       # comment 4 → Primary/600, resolved via styles list (2-hop)
        "disabled_opacity": 0.4,     # comment 6 only ("40% opacity")
    }
PY

# Required completion comment, anchored to the Button component-set node (read back by the verifier).
figma-cli comments add "$KEY" --node 2:0 \
  -m "Implemented Button states to the finalized spec: label 'Place order', height 48, padding-x 20, radius 10, default #2D6CDF, hover Primary/600 #1B4AA8, disabled 40% opacity."

echo "oracle: wrote button spec and posted completion comment"

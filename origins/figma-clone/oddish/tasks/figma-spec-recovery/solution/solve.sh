#!/bin/bash
# Oracle solution: recover the finalized PricingCard spec from the Figma file and
# write it into the codebase, then post the required completion comment.
#
# The values below are what an agent recovers by reading the node tree (geometry,
# heading, price, CTA color floats) AND the comment thread (final geometry review,
# the CTA-copy override that supersedes the stale "Sign up" node text).
set -euo pipefail
KEY="${FIGMA_FILE_KEY:-Pr1cingCardSpecFile001}"

cat > /workspace/pricing_card/card.py <<'PY'
"""PricingCard design-spec values — finalized to match the Figma design."""

from __future__ import annotations


def pricing_card_style() -> dict:
    return {
        "heading": "Pro",                 # node 1:3
        "price": "$29/mo",                # node 1:4 (only in the node tree)
        "card_padding": 24,               # node 1:2 + final review comment (decoy: v1 said 16)
        "card_gap": 16,                   # node 1:2 + final review comment (decoy: v1 said 12)
        "card_radius": 12,                # node 1:2 + final review comment (decoy: v1 said 8)
        "cta_label": "Start free trial",  # comment 4 overrides the stale node text "Sign up"
        "cta_color": "#1D4ED8",           # Primary/500 — node 1:6 fill / style token / comment 2
        "cta_radius": 8,                  # node 1:6
    }
PY

# Required completion comment, anchored to the PricingCard node (read back by the verifier).
export FIGMA_API_URL="${FIGMA_API_URL:-http://figma:3000}"
figma-cli comments add "$KEY" --node 1:2 \
  -m "Implemented PricingCard to the finalized spec: padding 24, gap 16, radius 12, CTA 'Start free trial' #1D4ED8 (r8)."

echo "oracle: wrote spec and posted completion comment"

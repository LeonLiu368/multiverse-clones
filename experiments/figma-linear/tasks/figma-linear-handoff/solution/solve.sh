#!/usr/bin/env bash
# Oracle: correlate the Linear ticket with the Figma design, implement the spec,
# move the ticket to In Review, and comment it.
set -euo pipefail
KEY="${FIGMA_FILE_KEY:-PrcCardHandoffFile001x}"
export FIGMA_API_URL="${FIGMA_API_URL:-http://figma:3000}"

# 1) Recover the finalized spec from the Figma file (node tree geometry + heading/price;
#    the CTA label override lives in the design comment thread, not on the stale node).
cat > /app/pricing_card/card.py <<'PY'
"""PricingCard design-spec values — finalized to match the Figma design."""

from __future__ import annotations


def pricing_card_spec() -> dict:
    return {
        "heading": "Pro",                 # node 1:3
        "price": "$29/mo",                # node 1:4
        "card_padding": 24,               # node 1:2 + geometry comment
        "card_radius": 12,                # node 1:2 + geometry comment
        "cta_label": "Start free trial",  # design comment 2 overrides the stale node text "Subscribe"
    }
PY

# 2) Move the ticket to In Review and record what was implemented.
linear issue update DES-101 --state "In Review"
linear issue comment add DES-101 --body "Implemented PricingCard to the finalized Figma spec: heading 'Pro', price \$29/mo, padding 24, radius 12, CTA 'Start free trial'."

echo "oracle: implemented spec, moved DES-101 to In Review, commented the ticket"

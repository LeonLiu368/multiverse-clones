"""PricingCard design-spec values.

Placeholder values from before the design was finalized — they do NOT match the
current design. Update them to match the finalized design referenced by the
Linear ticket (the Figma PricingCard component and its comment thread).

Return contract (do not change the keys or types):

    {
        "heading":      str,   # the plan name
        "price":        str,   # the price label
        "card_padding": int,   # inner padding (px), all sides
        "card_radius":  int,   # card corner radius (px)
        "cta_label":    str,   # the call-to-action button text
    }
"""

from __future__ import annotations


def pricing_card_spec() -> dict:
    return {
        "heading": "TODO",
        "price": "TODO",
        "card_padding": 0,
        "card_radius": 0,
        "cta_label": "TODO",
    }

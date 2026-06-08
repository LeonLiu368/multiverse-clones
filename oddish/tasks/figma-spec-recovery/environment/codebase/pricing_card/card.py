"""PricingCard design-spec values.

This module is the single place the front-end reads the PricingCard's spec from.
The values below are placeholders from before the design was finalized — they do
NOT match the current design. Update them to match the finalized design in Figma.

Return contract (do not change the keys or types):

    {
        "heading":      str,    # the plan name shown at the top of the card
        "price":        str,    # the price label
        "card_padding": int,    # inner padding (px), all sides
        "card_gap":     int,    # vertical gap between rows (px)
        "card_radius":  int,    # card corner radius (px)
        "cta_label":    str,    # the call-to-action button text
        "cta_color":    str,    # the CTA fill, as a "#RRGGBB" hex string
        "cta_radius":   int,    # the CTA button corner radius (px)
    }
"""

from __future__ import annotations


def pricing_card_style() -> dict:
    return {
        "heading": "TODO",
        "price": "TODO",
        "card_padding": 0,
        "card_gap": 0,
        "card_radius": 0,
        "cta_label": "TODO",
        "cta_color": "#000000",
        "cta_radius": 0,
    }

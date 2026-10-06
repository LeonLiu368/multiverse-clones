"""HIDDEN grader — pins the exact finalized PricingCard spec (figma-recovered).

heading/price/card_padding/card_radius come from the node tree (confirmed by the
geometry comment); cta_label requires reading the design comment thread — the node
still shows the stale "Subscribe", overridden to "Start free trial" by a later
comment. Filename starts with test_grade_ so pytest auto-collects it.
"""

from pricing_card import pricing_card_spec

EXPECTED = {
    "heading": "Pro",
    "price": "$29/mo",
    "card_padding": 24,
    "card_radius": 12,
    "cta_label": "Start free trial",
}


def test_spec_matches_design():
    s = pricing_card_spec()
    for k, want in EXPECTED.items():
        assert s[k] == want, f"{k}: expected {want!r}, got {s[k]!r}"

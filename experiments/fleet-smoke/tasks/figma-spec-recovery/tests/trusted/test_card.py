"""Visible, invariant-only checks for the PricingCard spec.

These verify the SHAPE of the spec — keys, types, basic format — never the
specific values (those live only in the Figma file and the hidden grader). The
agent can run these to iterate; passing them is necessary but not sufficient.
"""

import re

from pricing_card import pricing_card_style


def test_returns_dict_with_required_keys():
    style = pricing_card_style()
    assert isinstance(style, dict)
    assert set(style) == {
        "heading", "price", "card_padding", "card_gap", "card_radius",
        "cta_label", "cta_color", "cta_radius",
    }


def test_types_and_formats():
    s = pricing_card_style()
    for k in ("card_padding", "card_gap", "card_radius", "cta_radius"):
        assert isinstance(s[k], int) and s[k] >= 0, k
    for k in ("heading", "price", "cta_label"):
        assert isinstance(s[k], str) and s[k] and s[k] != "TODO", k
    assert isinstance(s["cta_color"], str)
    assert re.fullmatch(r"#[0-9A-Fa-f]{6}", s["cta_color"]), s["cta_color"]

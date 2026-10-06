"""Visible, invariant-only checks — shape/types only, never the buried values."""

from pricing_card import pricing_card_spec


def test_keys_and_types():
    s = pricing_card_spec()
    assert isinstance(s, dict)
    assert set(s) == {"heading", "price", "card_padding", "card_radius", "cta_label"}
    assert isinstance(s["card_padding"], int) and s["card_padding"] > 0
    assert isinstance(s["card_radius"], int) and s["card_radius"] > 0
    for k in ("heading", "price", "cta_label"):
        assert isinstance(s[k], str) and s[k] and s[k] != "TODO", k

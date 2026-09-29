"""HIDDEN grader — pins the exact finalized PricingCard spec.

The agent never sees this file. It encodes the values that can only be recovered
by reading the Figma file's node tree AND its comment thread:

  * card_padding / card_gap / card_radius  — node 1:2 (confirmed by the FINAL
    review comment; the v1 comment's 16/12/8 are superseded decoys).
  * cta_radius                              — node 1:6 (== 8; a trap for card_radius).
  * cta_color                               — Primary/500 #1D4ED8 (node 1:6 fill /
    style token / comment 2). Graded case-insensitively — format isn't the point.
  * heading / price                         — node tree (price "$29/mo" appears
    ONLY in the tree, so comment-only recovery fails).
  * cta_label                               — "Start free trial": node 1:7 still
    shows the STALE "Sign up"; comment 4 overrides it, so node-only recovery fails.

Filename MUST start with ``test_grade_`` — pytest auto-collects ``test_*.py``;
a ``grade_*.py`` would be silently skipped (a false-pass hole).
"""

from pricing_card import pricing_card_style

EXPECTED = {
    "heading": "Pro",
    "price": "$29/mo",
    "card_padding": 24,
    "card_gap": 16,
    "card_radius": 12,
    "cta_label": "Start free trial",
    "cta_radius": 8,
}


def test_geometry_and_copy():
    s = pricing_card_style()
    for key, want in EXPECTED.items():
        assert s[key] == want, f"{key}: expected {want!r}, got {s[key]!r}"


def test_cta_color():
    # grade substance, not format: #1D4ED8 in any case
    assert pricing_card_style()["cta_color"].lower() == "#1d4ed8"

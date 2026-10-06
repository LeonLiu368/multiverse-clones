"""HIDDEN grader — pins the exact finalized Button spec.

The agent never sees this file. The values can only be recovered by combining
THREE sources in the Figma file (no single read or single source suffices):

  * height            — ONLY in the node tree (component 2:1 absoluteBoundingBox.height;
                        comment 5 deliberately refuses to state it). Comment-only fails.
  * label             — comment 7 overrides the stale node text "Buy now". Node-only fails.
  * hover_bg          — comment 4 says "use the Primary/600 token", and the styles list
                        resolves Primary/600 → #143FB7 (a 2-hop lookup). The Hover node's
                        fill is a STALE bright blue. Node-only and comment-only both fail.
  * disabled_opacity  — ONLY in comment 6 ("40% opacity" → 0.4). Node-only fails.
  * padding_x/radius  — node 2:1 (confirmed by the FINAL comment 5; the v1/v2 comments'
                        8 and 12 are superseded decoys, and 8 also doubles as a cross-field trap).
  * default_bg        — Primary/500 #1D4ED8 (node fill / comment 2 / styles).

Colors graded case-insensitively and opacity within a tolerance — substance, not format.
Filename MUST start with ``test_grade_`` so pytest auto-collects it.
"""

from button_states import button_states_spec

EXPECTED = {
    "label": "Place order",
    "height": 48,
    "padding_x": 20,
    "radius": 10,
}


def test_geometry_and_copy():
    s = button_states_spec()
    for key, want in EXPECTED.items():
        assert s[key] == want, f"{key}: expected {want!r}, got {s[key]!r}"


def test_colors():
    s = button_states_spec()
    assert s["default_bg"].lower() == "#2d6cdf", s["default_bg"]
    assert s["hover_bg"].lower() == "#1b4aa8", s["hover_bg"]  # Primary/600, resolved via styles


def test_disabled_opacity():
    assert abs(float(button_states_spec()["disabled_opacity"]) - 0.4) < 1e-6

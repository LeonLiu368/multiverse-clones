"""Button design-spec values, consumed by the design-system theme layer.

The values below are stale placeholders from before the Button states were
finalized — they do NOT match the current design. Update them to match the
finalized design in Figma (the Button component set and its comment thread).

Return contract (do not change the keys or types):

    {
        "label":            str,    # the button's copy
        "height":           int,    # button height in px
        "padding_x":        int,    # horizontal padding in px
        "radius":           int,    # corner radius in px
        "default_bg":       str,    # Default-state fill, "#RRGGBB"
        "hover_bg":         str,    # Hover-state fill, "#RRGGBB"
        "disabled_opacity": float,  # Disabled-state opacity, 0.0–1.0
    }
"""

from __future__ import annotations


def button_states_spec() -> dict:
    return {
        "label": "TODO",
        "height": 0,
        "padding_x": 0,
        "radius": 0,
        "default_bg": "#000000",
        "hover_bg": "#000000",
        "disabled_opacity": 1.0,
    }

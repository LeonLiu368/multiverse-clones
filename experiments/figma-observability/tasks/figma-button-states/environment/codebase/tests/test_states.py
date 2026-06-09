"""Visible, invariant-only checks for the Button spec.

These verify the SHAPE of the spec — keys, types, format — never the specific
values (those live only in the Figma file and the hidden grader). The agent can
run these to iterate; passing them is necessary but not sufficient.
"""

import re

from button_states import button_states_spec


def test_returns_dict_with_required_keys():
    s = button_states_spec()
    assert isinstance(s, dict)
    assert set(s) == {
        "label", "height", "padding_x", "radius",
        "default_bg", "hover_bg", "disabled_opacity",
    }


def test_types_and_formats():
    s = button_states_spec()
    for k in ("height", "padding_x", "radius"):
        assert isinstance(s[k], int) and s[k] > 0, k
    assert isinstance(s["label"], str) and s["label"] and s["label"] != "TODO"
    for k in ("default_bg", "hover_bg"):
        assert isinstance(s[k], str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", s[k]), (k, s[k])
    assert isinstance(s["disabled_opacity"], (int, float))
    assert 0.0 < float(s["disabled_opacity"]) <= 1.0

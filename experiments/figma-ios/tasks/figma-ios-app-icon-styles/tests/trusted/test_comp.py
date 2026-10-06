"""Visible, invariant-only check — shape only, never the values."""
from ios_components import app_icon_styles

def test_returns_list_of_names():
    s = app_icon_styles()
    assert isinstance(s, list) and len(s) >= 1
    assert all(isinstance(x, str) and x for x in s)

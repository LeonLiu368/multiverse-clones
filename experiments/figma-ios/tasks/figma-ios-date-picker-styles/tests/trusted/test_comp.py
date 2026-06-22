"""Visible, invariant-only check — shape only, never the values."""
from ios_components import date_picker_styles

def test_returns_list_of_names():
    s = date_picker_styles()
    assert isinstance(s, list) and len(s) >= 1
    assert all(isinstance(x, str) and x for x in s)

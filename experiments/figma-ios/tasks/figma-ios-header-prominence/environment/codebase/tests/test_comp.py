"""Visible, invariant-only check — shape only, never the values."""
from ios_components import header_prominence_levels

def test_returns_list_of_names():
    s = header_prominence_levels()
    assert isinstance(s, list) and len(s) >= 1
    assert all(isinstance(x, str) and x for x in s)

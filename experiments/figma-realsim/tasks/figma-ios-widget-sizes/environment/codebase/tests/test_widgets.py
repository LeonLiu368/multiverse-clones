"""Visible, invariant-only check — shape only, never the values."""
from ios_widgets import home_screen_widget_sizes

def test_returns_list_of_names():
    s = home_screen_widget_sizes()
    assert isinstance(s, list) and len(s) >= 1
    assert all(isinstance(x, str) and x for x in s)

"""Visible, invariant-only check — shape only, never the value."""
from whois import greeting_name

def test_returns_nonempty_name():
    n = greeting_name()
    assert isinstance(n, str) and n and n != "TODO"

"""Visible, invariant-only check — shape only, never the value."""
import re
from launch import launch_date

def test_shape():
    d = launch_date()
    assert isinstance(d, str) and d != "TODO"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", d), d

"""HIDDEN grader — the values only exist in the Figma design (the
"App Icon/iPhone" component set variants). Order-insensitive."""
from ios_components import app_icon_styles

def test_matches_design():
    assert sorted(app_icon_styles()) == ['Custom', 'System']

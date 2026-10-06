"""HIDDEN grader — the values only exist in the Figma design (the
"Date and time - Pickers" component set variants). Order-insensitive."""
from ios_components import date_picker_styles

def test_matches_design():
    assert sorted(date_picker_styles()) == ['Compact', 'Inline']

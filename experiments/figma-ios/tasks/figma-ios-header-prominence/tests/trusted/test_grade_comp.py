"""HIDDEN grader — the values only exist in the Figma design (the
"Header" component set variants). Order-insensitive."""
from ios_components import header_prominence_levels

def test_matches_design():
    assert sorted(header_prominence_levels()) == ['Extra Prominent', 'Nested', 'Prominent']

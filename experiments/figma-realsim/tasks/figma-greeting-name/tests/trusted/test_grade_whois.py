"""HIDDEN grader — the name only exists in the Figma file's text layer.
The design TEXT reads 'Hello World!\\nMy name is Jaquavious'; the name is Jaquavious.
"""
from whois import greeting_name

def test_name_matches_design():
    assert greeting_name().strip() == "Jaquavious"

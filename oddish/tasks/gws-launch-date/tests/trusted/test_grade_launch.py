"""HIDDEN grader — the date exists only in the Q3 Launch Plan doc."""
from launch import launch_date

def test_date():
    assert launch_date() == "2026-09-15"

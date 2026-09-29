"""HIDDEN grader — answer requires chaining Gmail (which launch) -> Calendar (its date)."""
from launch import launch_date

def test_date():
    # 'Atlas Launch — GA' is the authoritative event per the final email; its start is 2026-10-06.
    assert launch_date() == "2026-10-06"

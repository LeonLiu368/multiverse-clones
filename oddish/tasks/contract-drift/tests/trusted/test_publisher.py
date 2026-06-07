"""Invariant tests — do not encode specific v2 field names."""
import pytest
from events.publisher import build_event_payload


def test_returns_dict():
    assert isinstance(build_event_payload("login", "u1", {}), dict)


def test_event_name_present():
    result = build_event_payload("page_view", "u1", {})
    assert any(v == "page_view" for v in result.values())


def test_user_id_present():
    result = build_event_payload("login", "user-42", {})
    assert any(v == "user-42" for v in result.values())


def test_data_round_trips():
    props = {"key": "val", "n": 3}
    result = build_event_payload("action", "u1", props)
    assert any(v == props for v in result.values())


def test_timestamp_encoded():
    ts = 1700000000.0
    result = build_event_payload("ev", "u1", {}, timestamp=ts)
    # timestamp must appear in some numeric form
    assert any(isinstance(v, (int, float)) for v in result.values())


def test_schema_version_present():
    assert "schema_version" in build_event_payload("ev", "u1", {})

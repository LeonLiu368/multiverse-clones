# HIDDEN grading test — never present in the agent's container during the run.
# Pins the exact v2 analytics-event schema from the #data-platform announcement.
from events.publisher import build_event_payload


def test_event_name_field():
    p = build_event_payload("login", "u1", {})
    assert "event_name" in p, "v2 uses 'event_name', not 'name'"
    assert p["event_name"] == "login"


def test_no_legacy_name_field():
    p = build_event_payload("login", "u1", {})
    assert "name" not in p, "v1 'name' field must be removed in v2"


def test_actor_id_field():
    p = build_event_payload("login", "u99", {})
    assert "actor_id" in p, "v2 uses 'actor_id' (not 'user_id' or 'author_id')"
    assert p["actor_id"] == "u99"


def test_no_legacy_user_id_field():
    p = build_event_payload("login", "u1", {})
    assert "user_id" not in p, "v1 'user_id' field must be removed in v2"


def test_attributes_field():
    props = {"page": "/home", "ref": "direct"}
    p = build_event_payload("page_view", "u1", props)
    assert "attributes" in p, "v2 uses 'attributes', not 'data'"
    assert p["attributes"] == props


def test_no_legacy_data_field():
    p = build_event_payload("ev", "u1", {})
    assert "data" not in p, "v1 'data' field must be removed in v2"


def test_recorded_at_int_milliseconds():
    ts = 1700000000.0
    p = build_event_payload("ev", "u1", {}, timestamp=ts)
    assert "recorded_at" in p, "v2 uses 'recorded_at', not 'timestamp'"
    assert "timestamp" not in p, "v1 'timestamp' field must be removed in v2"
    assert isinstance(p["recorded_at"], int), "recorded_at must be an integer"
    assert p["recorded_at"] == 1700000000000, "recorded_at must be milliseconds (× 1000)"


def test_schema_version_int_two():
    p = build_event_payload("ev", "u1", {})
    assert p.get("schema_version") == 2, "schema_version must be integer 2"
    assert isinstance(p.get("schema_version"), int), "schema_version must be int, not str '2'"

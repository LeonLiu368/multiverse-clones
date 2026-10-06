"""Pipeline integration tests (correct, should already pass)."""
from events.pipeline import emit


def test_emit_returns_dict():
    result = emit("login", "u1")
    assert isinstance(result, dict)
    assert result.get("queued") is True


def test_emit_includes_payload():
    result = emit("signup", "u2", {"plan": "pro"})
    assert "payload" in result
    assert isinstance(result["payload"], dict)

"""Invariant tests for RateLimitMiddleware."""
from ratelimit.middleware import RateLimitMiddleware


def test_allow_returns_dict():
    m = RateLimitMiddleware()
    result = m.allow("client-1")
    assert isinstance(result, dict)
    assert "allowed" in result
    assert "remaining" in result
    assert "client_id" in result


def test_client_id_echoed():
    m = RateLimitMiddleware()
    assert m.allow("my-client")["client_id"] == "my-client"


def test_fresh_allows_first_request():
    m = RateLimitMiddleware()
    assert m.allow()["allowed"] is True

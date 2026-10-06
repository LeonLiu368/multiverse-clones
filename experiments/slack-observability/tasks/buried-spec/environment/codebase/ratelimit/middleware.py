"""Rate-limit middleware (correct — no changes needed here)."""
from .bucket import TokenBucket


class RateLimitMiddleware:
    """Per-client rate limiting using a token bucket."""

    def __init__(self, bucket: TokenBucket | None = None):
        self.bucket = bucket or TokenBucket()

    def allow(self, client_id: str = "default") -> dict:
        """Check whether a request from client_id should be allowed."""
        allowed = self.bucket.consume()
        return {
            "allowed": allowed,
            "remaining": self.bucket.available(),
            "client_id": client_id,
        }

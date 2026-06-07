"""Token-bucket rate limiter.

The production values for this limiter were revised after load testing.
The agreed configuration is in the workspace — check #platform-infra.
"""
from dataclasses import dataclass, field
import time

# These values were revised after the load-test exercise. Recover the agreed
# configuration from the workspace (#platform-infra discussion) and update them.
CAPACITY = 50            # max tokens (burst ceiling)
REFILL_RATE = 5.0        # tokens added per second
INITIAL_TOKENS = 50      # tokens available at startup
OVERDRAFT_ALLOWANCE = 5  # tokens allowed beyond CAPACITY (set to 0 for strict limiting)


@dataclass
class TokenBucket:
    capacity: int = CAPACITY
    refill_rate: float = REFILL_RATE
    initial_tokens: int = INITIAL_TOKENS
    overdraft_allowance: int = OVERDRAFT_ALLOWANCE

    _tokens: float = field(default=0.0, init=False, repr=False)
    _last_refill: float = field(default=0.0, init=False, repr=False)

    def __post_init__(self):
        self._tokens = float(self.initial_tokens)
        self._last_refill = time.monotonic()

    def _refill(self, now: float) -> None:
        elapsed = now - self._last_refill
        self._tokens = min(
            self.capacity + self.overdraft_allowance,
            self._tokens + elapsed * self.refill_rate,
        )
        self._last_refill = now

    def consume(self, tokens: int = 1) -> bool:
        """Try to consume tokens. Returns True if allowed, False if rate limited."""
        self._refill(time.monotonic())
        if self._tokens >= tokens:
            self._tokens -= tokens
            return True
        return False

    def available(self) -> int:
        """Current available token count (floor)."""
        self._refill(time.monotonic())
        return max(0, int(self._tokens))

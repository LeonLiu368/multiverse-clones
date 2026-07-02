"""Discord snowflake identifiers.

Discord addresses every object — guilds, channels, messages, users, roles — by a
**snowflake**: a 64-bit integer rendered as a decimal *string* (e.g.
``"175928847299117063"``). The high 42 bits are a millisecond timestamp since the
Discord epoch (2015-01-01); the low bits are worker/process/increment. The real API
always returns the stringified form and accepts it on input, so we mirror that: a
snowflake carries a real creation time you can recover, and lexicographic-by-length
ordering equals chronological ordering.

Pass a seeded ``Snowflake`` generator for deterministic corpora (R1.6 determinism):
the same seed → byte-identical ids.
"""

from __future__ import annotations

import threading
import time

# Discord epoch: 2015-01-01T00:00:00.000Z in milliseconds.
DISCORD_EPOCH = 1420070400000


def timestamp_of(snowflake: str | int) -> int:
    """Recover the millisecond unix timestamp encoded in a snowflake."""
    return (int(snowflake) >> 22) + DISCORD_EPOCH


def iso_of(snowflake: str | int) -> str:
    """The ISO-8601 creation timestamp a snowflake encodes (Discord renders these)."""
    from .store import iso_from_ms

    return iso_from_ms(timestamp_of(snowflake))


def make_snowflake(ms: int, increment: int = 0, worker: int = 1, process: int = 0) -> str:
    """Assemble a snowflake string from a ms timestamp + the low-bit fields."""
    rel = max(0, int(ms) - DISCORD_EPOCH)
    value = (rel << 22) | ((worker & 0x1F) << 17) | ((process & 0x1F) << 12) | (increment & 0xFFF)
    return str(value)


class Snowflake:
    """A monotonic snowflake generator.

    ``Snowflake()`` mints ids from wall-clock time (the gateway's runtime path for
    freshly-posted messages). ``Snowflake(seed_ms=…)`` mints a deterministic,
    strictly-increasing sequence from a fixed base — used by the seed generator so a
    corpus is byte-identical across builds.
    """

    def __init__(self, seed_ms: int | None = None, worker: int = 1, process: int = 0) -> None:
        self._worker = worker
        self._process = process
        self._increment = 0
        self._deterministic = seed_ms is not None
        self._cursor_ms = seed_ms if seed_ms is not None else 0
        self._last_ms = 0
        self._lock = threading.Lock()

    def next(self) -> str:
        with self._lock:
            if self._deterministic:
                # Advance a synthetic clock: bump the increment, roll to the next ms
                # when it saturates. Strictly increasing → snowflake order == insert order.
                self._increment += 1
                if self._increment > 0xFFF:
                    self._increment = 0
                    self._cursor_ms += 1
                ms = self._cursor_ms
            else:
                ms = int(time.time() * 1000)
                if ms <= self._last_ms:
                    ms = self._last_ms
                    self._increment = (self._increment + 1) & 0xFFF
                    if self._increment == 0:
                        ms += 1
                else:
                    self._increment = 0
                self._last_ms = ms
            return make_snowflake(ms, self._increment, self._worker, self._process)


# A shared runtime generator for gateway writes (posted messages, reactions row ids).
_runtime = Snowflake()


def gen_snowflake() -> str:
    """Mint a fresh runtime snowflake (wall-clock based, monotonic)."""
    return _runtime.next()


def is_snowflake(value: str) -> bool:
    if not value:
        return False
    v = str(value).strip()
    return v.isdigit() and 1 <= len(v) <= 20

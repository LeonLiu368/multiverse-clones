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


# A fixed base time (2020-01-01T00:00:00Z in ms) for synthesized ids that carry no
# real creation time (generic datasets keyed only by a name/handle string).
SYNTH_BASE_MS = 1577836800000


def stable_snowflake(key: str, *, kind: str = "") -> str:
    """A deterministic snowflake derived from a source key (e.g. an author handle or
    channel name in a dataset that has no real snowflake).

    The same ``(kind, key)`` always maps to the same snowflake, so re-importing the
    same source is byte-identical (R1.6) and cross-references (a message's author →
    the user row) resolve. The hash is folded into the low 22 bits (worker/process/
    increment) over a spread of synthetic milliseconds above ``SYNTH_BASE_MS``, so
    the value is a well-formed, monotone-decodable snowflake — never colliding with a
    real Discord id range for the same string by accident.
    """
    import hashlib

    h = int(hashlib.sha256(f"{kind}\x00{key}".encode()).hexdigest(), 16)
    # Spread across ~ 2^31 ms (~24 days) above the base so distinct keys rarely share
    # a ms; the low 22 bits carry the rest of the entropy.
    ms = SYNTH_BASE_MS + (h % (1 << 31))
    low = (h >> 31) & 0x3FFFFF  # 22 bits
    rel = ms - DISCORD_EPOCH
    return str((rel << 22) | low)


def is_snowflake(value: str) -> bool:
    if not value:
        return False
    v = str(value).strip()
    return v.isdigit() and 1 <= len(v) <= 20

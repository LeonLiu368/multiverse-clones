"""Notion-style identifiers.

Notion's public API addresses every object — pages, databases, blocks, users,
comments — by a **UUIDv4** rendered in the dashed 8-4-4-4-12 form
(``"680dee41-b447-405e-bb4b-9bbeec0b3a3a"``). The API accepts both the dashed and
the 32-char compact form on input and always returns the dashed form, so we mirror
that exactly.

Pass a seeded ``random.Random`` for deterministic generation so the same inputs
produce a byte-identical corpus (R1.6 determinism).
"""

from __future__ import annotations

import random
import uuid


def gen_uuid(rng: random.Random | None = None) -> str:
    """Generate a dashed UUIDv4 string, deterministic when ``rng`` is seeded."""
    r = rng or random
    return str(uuid.UUID(int=r.getrandbits(128), version=4))


def normalize_id(value: str) -> str:
    """Accept the compact 32-char form Notion also takes and return the dashed form.

    Invalid input is returned unchanged so the caller's lookup simply misses
    (-> object_not_found) rather than raising — matching Notion, which 404s on a
    well-formed-but-unknown id and validation-errors on a malformed one.
    """
    if not value:
        return value
    v = value.strip()
    try:
        return str(uuid.UUID(v))
    except (ValueError, AttributeError):
        return v


def is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except (ValueError, AttributeError, TypeError):
        return False

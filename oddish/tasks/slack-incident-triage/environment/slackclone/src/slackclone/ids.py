"""Slack-style identifiers and opaque pagination cursors.

Slack IDs look like ``U0AB12CD34`` (users) and ``C0AB12CD34`` (channels), and a
message id is a ``ts`` string ``"<epoch_seconds>.<6-digit-sequence>"`` that is
unique within a channel. We mirror those conventions so an agent's Slack
knowledge (and real Slack SDKs) transfer unchanged.
"""

from __future__ import annotations

import base64
import json
import random
import string

_ALPHABET = string.ascii_uppercase + string.digits


def gen_id(prefix: str, rng: random.Random | None = None, length: int = 9) -> str:
    """Generate a Slack-style id, e.g. ``gen_id("U")`` -> ``"U0AB12CD3"``.

    Pass a seeded ``random.Random`` for deterministic generation.
    """
    r = rng or random
    return prefix + "".join(r.choice(_ALPHABET) for _ in range(length))


def make_ts(epoch_seconds: float, seq: int) -> str:
    """Build a Slack ``ts`` message id from an epoch and a per-second sequence."""
    return f"{int(epoch_seconds)}.{seq % 1_000_000:06d}"


def encode_cursor(offset: int) -> str:
    """Opaque base64 cursor carrying the next offset (Slack-style)."""
    return base64.urlsafe_b64encode(json.dumps({"offset": offset}).encode()).decode()


def decode_cursor(cursor: str | None) -> int:
    if not cursor:
        return 0
    try:
        return int(json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())["offset"])
    except Exception:
        return 0

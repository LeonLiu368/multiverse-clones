"""Figma-style identifiers.

Figma uses three id shapes an agent's Figma knowledge (and real Figma SDKs)
relies on, so we mirror them exactly:

* **file keys** — 22-char URL-safe tokens (``"a1B2c3D4e5F6g7H8i9J0kL"``) that
  appear in a file URL ``figma.com/file/<key>/...``.
* **node ids** — ``"<a>:<b>"`` pairs (``"1:23"``); the document root is ``"0:0"``
  and each canvas/frame/node gets a stable pair. The colon form is what
  ``GET /v1/files/:key/nodes?ids=1:23`` expects (the API also tolerates the
  hyphen form ``1-23`` used in deep links).
* **comment ids** — short decimal strings, monotonically increasing per file,
  mirroring Figma's ``order_id``/``id`` convention.

Pass a seeded ``random.Random`` for deterministic generation so the same inputs
produce a byte-identical file.
"""

from __future__ import annotations

import random
import string

_KEY_ALPHABET = string.ascii_letters + string.digits


def gen_file_key(rng: random.Random | None = None, length: int = 22) -> str:
    """Generate a Figma-style 22-char file key."""
    r = rng or random
    return "".join(r.choice(_KEY_ALPHABET) for _ in range(length))


def make_node_id(major: int, minor: int) -> str:
    """Build a Figma node id ``"<major>:<minor>"`` (root is ``"0:0"``)."""
    return f"{major}:{minor}"


def normalize_node_id(node_id: str) -> str:
    """Accept the hyphen form (``1-23``) deep links use and return the API form."""
    return node_id.replace("-", ":", 1) if "-" in node_id and ":" not in node_id else node_id


def gen_comment_id(seq: int) -> str:
    """Comment id / order_id — a per-file monotonic decimal string."""
    return str(seq)

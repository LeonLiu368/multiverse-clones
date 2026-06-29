"""Google Workspace-style identifiers.

Google uses opaque, URL-safe ids that an agent's Google knowledge / real SDKs
treat as black boxes, so we mirror the *shape* (length + alphabet), not any
internal structure:

* **Drive file / Docs document ids** — ~44-char URL-safe tokens
  (``"1A2b3C..._-"``). A Google Doc *is* a Drive file, so its ``documentId``
  equals its Drive file id (we keep that invariant in the seed).
* The synthetic root folder is ``"root"`` (Drive's alias for the My Drive root).

Pass a seeded ``random.Random`` for deterministic generation.
"""

from __future__ import annotations

import random
import string

_ALPHABET = string.ascii_letters + string.digits + "-_"


def gen_file_id(rng: random.Random | None = None, length: int = 44) -> str:
    """Generate a Drive/Docs-style id (also used as a Doc's documentId)."""
    r = rng or random
    return "".join(r.choice(_ALPHABET) for _ in range(length))

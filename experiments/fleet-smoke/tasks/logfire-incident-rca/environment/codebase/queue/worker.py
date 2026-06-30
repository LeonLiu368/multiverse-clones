"""Worker slot-leasing logic.

`lease_slot` stamps the lock-timestamp column when it grabs a slot. If that column is
not in the table schema (`SLOT_COLUMNS`), the UPDATE references a non-existent column —
the production failure. `lease_slot` here validates against the schema so the bug is
reproducible offline (and fixable by adding the column to the schema).
"""
from __future__ import annotations

from queue.models import SLOT_COLUMNS

# The column the worker stamps when it leases a slot.
LOCK_COLUMN = "locked_at"


def lease_slot(slot_id: int, worker: str, now: str) -> dict:
    """Lease a slot: set leased_by + the lock timestamp. Raises if the lock column is
    missing from the table schema (mirrors asyncpg UndefinedColumnError in prod)."""
    if LOCK_COLUMN not in SLOT_COLUMNS:
        raise KeyError(
            f'column "{LOCK_COLUMN}" of relation "queue_slots" does not exist'
        )
    return {"id": slot_id, "leased_by": worker, LOCK_COLUMN: now}

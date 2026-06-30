"""Worker queue schema.

`queue_slots` backs the worker's slot-leasing. The worker leases a slot by stamping a
lock timestamp, so the schema MUST carry every column the worker writes — a column the
ORM model references but the table doesn't have raises asyncpg UndefinedColumnError at
runtime (which is exactly how the current incident manifests in production telemetry).

The DDL below is the source of truth for the table; `SLOT_COLUMNS` must match it. Right
now the lock-timestamp column the worker needs is MISSING from both.
"""
from __future__ import annotations

# Columns that exist on the `queue_slots` table today (the migration that adds the
# worker's lock-timestamp column was never applied — see the production incident).
SLOT_COLUMNS = [
    "id",
    "task_id",
    "leased_by",
    "created_at",
]


def create_table_ddl() -> str:
    cols = ",\n  ".join(_DDL_TYPES[c] for c in SLOT_COLUMNS)
    return f"CREATE TABLE queue_slots (\n  {cols}\n)"


_DDL_TYPES = {
    "id": "id BIGINT PRIMARY KEY",
    "task_id": "task_id TEXT NOT NULL",
    "leased_by": "leased_by TEXT",
    "created_at": "created_at TIMESTAMP NOT NULL",
    # locked_at: TIMESTAMP  <-- the column the worker writes; add it to fix the incident.
}

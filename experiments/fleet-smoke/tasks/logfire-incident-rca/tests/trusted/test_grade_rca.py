"""HIDDEN grader — pins the EXACT root cause recovered from the production telemetry.

These values are derived from the baked incident corpus (oddish-worker emitting
asyncpg UndefinedColumnError on `queue_slots.locked_at`, 60 records in the window).
They are NOT in the repo: the only way to get them is to query the `logfire` tools.
"""
from incident_rca import root_cause
from queue.models import SLOT_COLUMNS
from queue.worker import LOCK_COLUMN, lease_slot


def test_schema_fix_applied():
    # The missing column was added to the table schema.
    assert "locked_at" in SLOT_COLUMNS
    assert LOCK_COLUMN == "locked_at"
    # And the worker can now lease a slot without raising.
    row = lease_slot(1, "w", "2026-06-25T00:00:00Z")
    assert row["locked_at"] == "2026-06-25T00:00:00Z"


def test_rca_values_exact():
    rc = root_cause()
    assert rc["exception_type"] == "asyncpg.exceptions.UndefinedColumnError"
    assert rc["service"] == "oddish-worker"
    assert rc["table"] == "queue_slots"
    assert rc["missing_column"] == "locked_at"
    assert rc["occurrences"] == 60

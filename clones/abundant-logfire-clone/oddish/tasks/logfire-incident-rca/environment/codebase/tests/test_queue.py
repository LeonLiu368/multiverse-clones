"""Visible invariant tests. These check the SHAPE of the fix and RCA, not the actual
values — the values live in the production telemetry, not the repo. Run with:

    cd /workspace && python3 -m pytest tests/ -q
"""
from incident_rca import root_cause
from queue.models import SLOT_COLUMNS
from queue.worker import LOCK_COLUMN, lease_slot


def test_lock_column_present_in_schema():
    # The fix: the worker's lock-timestamp column must exist on the table schema.
    assert LOCK_COLUMN in SLOT_COLUMNS


def test_lease_slot_succeeds_once_schema_fixed():
    row = lease_slot(7, "worker-1", "2026-06-25T00:00:00Z")
    assert row["id"] == 7
    assert row["leased_by"] == "worker-1"
    assert LOCK_COLUMN in row


def test_rca_shape():
    rc = root_cause()
    assert set(rc) == {"exception_type", "service", "table", "missing_column", "occurrences"}
    assert isinstance(rc["exception_type"], str) and rc["exception_type"]
    assert isinstance(rc["service"], str) and rc["service"]
    assert isinstance(rc["table"], str) and rc["table"]
    assert isinstance(rc["missing_column"], str) and rc["missing_column"]
    assert isinstance(rc["occurrences"], int) and rc["occurrences"] > 0

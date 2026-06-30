"""Incident RCA — fill this in from what you find in the telemetry.

The worker is throwing a database error in production. Use the `logfire` tools to query
the telemetry (`records`) and recover the exact root cause, then return it here AND apply
the schema fix in `queue/models.py`.

Replace every "" / None below with the value recovered from the telemetry. Keep the keys
and types. The hidden grader pins the exact values; the visible tests check only the shape.
"""
from __future__ import annotations


def root_cause() -> dict:
    return {
        # The fully-qualified exception type seen in the telemetry (e.g. "pkg.mod.ErrorName").
        "exception_type": "",
        # The service_name that emits the failing records.
        "service": "",
        # The database table (relation) named in the error.
        "table": "",
        # The column that does not exist on that table.
        "missing_column": "",
        # How many records carry this exception in the incident window.
        "occurrences": None,
    }

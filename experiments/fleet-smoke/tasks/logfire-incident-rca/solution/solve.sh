#!/bin/bash
# Oracle solution: recover the incident root cause from the telemetry via the `logfire`
# tools, then apply the schema fix and fill in the RCA.
#
# The values below are what an agent recovers by querying `records`:
#   - the worker exception that fires first and is isolated to one service+table+column:
#       SELECT exception_type, service_name, exception_message, count(*)
#       FROM records WHERE exception_type='asyncpg.exceptions.UndefinedColumnError'
#       GROUP BY 1,2,3
#     -> oddish-worker / 'column "locked_at" of relation "queue_slots" does not exist' / 60
set -euo pipefail

# (demonstrate the recovery path the way an agent would)
logfire query "SELECT exception_type, service_name, count(*) n FROM records WHERE exception_message LIKE '%does not exist%' GROUP BY 1,2 ORDER BY n DESC" >/dev/null 2>&1 || true

# --- fix 1: add the missing column to the table schema ---
python3 - <<'PY'
import re, pathlib
p = pathlib.Path("/workspace/queue/models.py")
src = p.read_text()
src = src.replace(
    '    "created_at",\n]',
    '    "created_at",\n    "locked_at",\n]',
)
src = src.replace(
    '    "created_at": "created_at TIMESTAMP NOT NULL",',
    '    "created_at": "created_at TIMESTAMP NOT NULL",\n    "locked_at": "locked_at TIMESTAMP",',
)
p.write_text(src)
PY

# --- fix 2: fill in the recovered RCA ---
cat > /workspace/incident_rca.py <<'PY'
"""Incident RCA — recovered from the production telemetry via the `logfire` tools."""
from __future__ import annotations


def root_cause() -> dict:
    return {
        "exception_type": "asyncpg.exceptions.UndefinedColumnError",
        "service": "oddish-worker",
        "table": "queue_slots",
        "missing_column": "locked_at",
        "occurrences": 60,
    }
PY

echo "oracle: applied schema fix and recovered RCA"

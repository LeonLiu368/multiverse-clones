#!/usr/bin/env bash
# Oracle: recover the launch date from the Q3 Launch Plan Google Doc and write it.
# (agent recovers via:  gws-cli drive ls -q "name contains 'Launch'"  -> DOC id
#                       gws-cli docs text <id>  -> "Launch date: 2026-09-15")
set -euo pipefail
cat > /app/launch/plan.py <<'PY'
"""The Q3 launch date (recovered from the Q3 Launch Plan Google Doc)."""
from __future__ import annotations


def launch_date() -> str:
    return "2026-09-15"
PY
echo "oracle: wrote launch date"

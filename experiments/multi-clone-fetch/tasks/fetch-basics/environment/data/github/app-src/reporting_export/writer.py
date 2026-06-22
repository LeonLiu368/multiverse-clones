"""Minimal CSV writer for the reporting dashboard export."""
from __future__ import annotations

import csv
import io
from typing import Iterable, Sequence


def to_csv(header: Sequence[str], rows: Iterable[Sequence[object]]) -> str:
    """Render rows to a CSV string. (BOM handling for Excel is tracked in the issues.)"""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    for row in rows:
        w.writerow(row)
    return buf.getvalue()

from __future__ import annotations

from typing import Any


def shape_commit(commit: dict[str, Any]) -> dict[str, Any]:
    shaped = dict(commit)
    shaped.setdefault("shortId", str(commit.get("id", ""))[:7])
    return shaped

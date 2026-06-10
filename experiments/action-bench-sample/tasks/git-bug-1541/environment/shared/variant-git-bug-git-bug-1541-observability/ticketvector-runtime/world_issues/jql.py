from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .errors import UnsupportedCommandError


@dataclass(frozen=True)
class ParsedJQL:
    filters: dict[str, Any]
    order_by: str | None = None


def parse_jql(query: str) -> ParsedJQL:
    filters: dict[str, Any] = {}
    remaining = query.strip()
    order_match = re.search(r"\border\s+by\s+updated\s+(asc|desc)\s*$", remaining, re.I)
    order_by = None
    if order_match:
        order_by = "updated:" + order_match.group(1).lower()
        remaining = remaining[: order_match.start()].strip()
    clauses = [part.strip() for part in re.split(r"\band\b", remaining, flags=re.I) if part.strip()]
    for clause in clauses:
        if re.fullmatch(r"assignee\s*=\s*me", clause, re.I):
            filters["assignee"] = "me"
        elif match := re.fullmatch(r"status\s*!=\s*\"?([^\"\n]+)\"?", clause, re.I):
            filters["state_ne"] = match.group(1).strip()
        elif match := re.fullmatch(r"status\s*=\s*\"?([^\"\n]+)\"?", clause, re.I):
            filters["state"] = match.group(1).strip()
        elif match := re.fullmatch(r"project\s*=\s*([A-Za-z0-9_-]+)", clause, re.I):
            filters["project"] = match.group(1)
        elif match := re.fullmatch(r"label\s*=\s*([A-Za-z0-9_-]+)", clause, re.I):
            filters["label"] = match.group(1)
        elif match := re.fullmatch(r"priority\s+in\s*\(([^)]+)\)", clause, re.I):
            filters["priority"] = [part.strip().lower() for part in match.group(1).split(",")]
        elif match := re.fullmatch(r"text\s*~\s*\"([^\"]+)\"", clause, re.I):
            filters["search"] = match.group(1)
        elif re.fullmatch(r"sprint\s+is\s+empty", clause, re.I):
            filters["cycle_empty"] = True
        else:
            raise UnsupportedCommandError(
                f"unsupported JQL clause: {clause}. Use linear issue query filters for complex searches."
            )
    return ParsedJQL(filters=filters, order_by=order_by)


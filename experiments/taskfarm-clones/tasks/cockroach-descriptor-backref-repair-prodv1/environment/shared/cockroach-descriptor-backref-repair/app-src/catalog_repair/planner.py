from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


BACKREF_STACK_KEY = "sql.schema.validation_errors.read.backward_references.relation"


@dataclass(frozen=True)
class Repair:
    relation_id: int
    relation_name: str
    referenced_descriptor_id: int
    action: str
    reason: str


def plan_repairs(rows: Iterable[dict]) -> list[Repair]:
    """Return relation backrefs that should be removed before unsafe descriptor reads retry."""
    repairs: list[Repair] = []
    for row in rows:
        if row.get("stack_key") != BACKREF_STACK_KEY:
            continue
        repairs.append(
            Repair(
                relation_id=int(row["relation_id"]),
                relation_name=str(row["relation_name"]),
                referenced_descriptor_id=int(row["referenced_descriptor_id"]),
                action="remove_depended_on_by_backref",
                reason="depended-on-by relation validation failed during unsafe descriptor read",
            )
        )
    return repairs

from __future__ import annotations

from typing import Any

from .state_snapshot import mutation_log


def mutations() -> list[dict[str, Any]]:
    return mutation_log()

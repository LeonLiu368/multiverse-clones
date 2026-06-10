from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .errors import UnsupportedCommandError


@dataclass
class BootstrapResult:
    method: str
    base_url: str
    api_key: str


def bootstrap_plane(*args: Any, **kwargs: Any) -> BootstrapResult:
    raise UnsupportedCommandError("Plane bootstrap is not available in the task-safe agent runtime")


def detect_capabilities(*args: Any, **kwargs: Any) -> dict[str, Any]:
    raise UnsupportedCommandError("Plane capabilities are not available in the task-safe agent runtime")


def doctor(*args: Any, **kwargs: Any) -> dict[str, Any]:
    raise UnsupportedCommandError("Plane doctor is not available in the task-safe agent runtime")


def local_doctor(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return {"ok": True, "runtime": "task-safe-ticketvector", "plane": "disabled"}

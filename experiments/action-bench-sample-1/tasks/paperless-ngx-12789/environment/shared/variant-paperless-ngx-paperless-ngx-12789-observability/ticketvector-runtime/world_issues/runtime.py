from __future__ import annotations

from pathlib import Path
from typing import Any

from .errors import UnsupportedCommandError, redact


def grade_task(*args: Any, **kwargs: Any) -> dict[str, Any]:
    raise UnsupportedCommandError("runtime grading is not available in the task-safe agent runtime")


def runtime_doctor(*args: Any, **kwargs: Any) -> dict[str, Any]:
    raise UnsupportedCommandError("runtime doctor is not available in the task-safe agent runtime")


def runtime_status(*args: Any, **kwargs: Any) -> dict[str, Any]:
    raise UnsupportedCommandError("runtime status is not available in the task-safe agent runtime")


def write_agent_env(*args: Any, **kwargs: Any) -> dict[str, Any]:
    raise UnsupportedCommandError("agent env export is not available in the task-safe agent runtime")


def redact_file(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    target.write_text(redact(text), encoding="utf-8")
    return {"ok": True, "path": str(target)}

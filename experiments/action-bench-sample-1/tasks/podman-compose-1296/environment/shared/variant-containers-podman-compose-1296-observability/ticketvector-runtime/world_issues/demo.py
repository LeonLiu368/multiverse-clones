from __future__ import annotations

from typing import Any

from .errors import UnsupportedCommandError


def run_payments_triage(*args: Any, **kwargs: Any) -> dict[str, Any]:
    raise UnsupportedCommandError("demo commands are not available in the task-safe agent runtime")


def transcript(*args: Any, **kwargs: Any) -> str:
    raise UnsupportedCommandError("demo commands are not available in the task-safe agent runtime")

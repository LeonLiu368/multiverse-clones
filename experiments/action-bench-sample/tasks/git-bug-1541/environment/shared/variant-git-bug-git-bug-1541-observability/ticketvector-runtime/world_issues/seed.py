from __future__ import annotations

from typing import Any

from .errors import UnsupportedCommandError


def apply_seed(*args: Any, **kwargs: Any) -> dict[str, Any]:
    raise UnsupportedCommandError("seed commands are not available in the task-safe agent runtime")


def reset_seed(*args: Any, **kwargs: Any) -> dict[str, Any]:
    raise UnsupportedCommandError("seed commands are not available in the task-safe agent runtime")


def verify_seed(*args: Any, **kwargs: Any) -> dict[str, Any]:
    raise UnsupportedCommandError("seed commands are not available in the task-safe agent runtime")

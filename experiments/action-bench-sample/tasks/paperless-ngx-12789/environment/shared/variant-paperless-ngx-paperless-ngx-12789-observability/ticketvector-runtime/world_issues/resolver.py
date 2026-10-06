from __future__ import annotations

from typing import Any

from .errors import NotFoundError


def resolve_issue(backend: Any, value: str) -> dict[str, Any]:
    return backend.get_issue(value)


def resolve_project(backend: Any, value: str) -> dict[str, Any]:
    for project in backend.project_list():
        if value.lower() in {project["id"].lower(), project["key"].lower(), project["name"].lower()}:
            return project
    raise NotFoundError(f"project not found: {value}")


def resolve_name(items: list[dict[str, Any]], value: str, kind: str) -> dict[str, Any]:
    for item in items:
        if value.lower() in {str(item.get("id", "")).lower(), str(item.get("name", "")).lower()}:
            return item
    raise NotFoundError(f"{kind} not found: {value}")


from __future__ import annotations

from typing import Any

from .state import SentryStore


def list_projects(store: SentryStore, org_slug: str) -> list[dict[str, Any]]:
    return [_shape_project(item) for item in store.projects(org_slug)]


def get_project(store: SentryStore, org_slug: str, project_slug: str) -> dict[str, Any] | None:
    project = store.project(project_slug, org_slug)
    return _shape_project(project) if project else None


def _shape_project(project: dict[str, Any]) -> dict[str, Any]:
    shaped = dict(project)
    shaped.setdefault("slug", project.get("slug"))
    shaped.setdefault("name", project.get("name", project.get("slug")))
    shaped.setdefault("platform", project.get("platform", "unknown"))
    shaped.setdefault("team", {"slug": project.get("team_slug")})
    return shaped

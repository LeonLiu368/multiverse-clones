from __future__ import annotations

from typing import Any

from .state import SentryStore


def list_releases(store: SentryStore, org_slug: str, project_slug: str | None = None) -> list[dict[str, Any]]:
    return store.releases(org_slug, project_slug)


def get_release(store: SentryStore, org_slug: str, version: str, project_slug: str | None = None) -> dict[str, Any] | None:
    return store.release(version, org_slug, project_slug)


def release_commits(store: SentryStore, org_slug: str, version: str, project_slug: str | None = None) -> list[dict[str, Any]]:
    release = get_release(store, org_slug, version, project_slug)
    if not release:
        return []
    return release.get("commits", [])

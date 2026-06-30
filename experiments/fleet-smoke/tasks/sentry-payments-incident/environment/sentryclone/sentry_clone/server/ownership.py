from __future__ import annotations

from typing import Any

from .state import SentryStore


def list_rules(store: SentryStore, project_slug: str | None = None) -> list[dict[str, Any]]:
    return store.ownership_rules(project_slug)

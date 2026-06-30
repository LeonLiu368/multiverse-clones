from __future__ import annotations

from typing import Any

from .state import SentryStore


def list_organizations(store: SentryStore) -> list[dict[str, Any]]:
    return store.organizations()


def current_user(store: SentryStore) -> dict[str, Any]:
    user = store.current_user()
    org = store.org_slug()
    return {
        "id": user.get("id"),
        "email": user.get("email"),
        "name": user.get("name"),
        "username": user.get("username", user.get("email")),
        "org": org,
        "orgs": store.organizations(),
    }

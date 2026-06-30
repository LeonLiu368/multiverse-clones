from __future__ import annotations

from typing import Any

from .state import SentryStore


def list_comments(store: SentryStore, issue_ref: str) -> list[dict[str, Any]]:
    return store.comments(issue_ref)


def add_comment(store: SentryStore, issue_ref: str, text: str) -> dict[str, Any]:
    return store.add_comment(issue_ref, text)


def list_activity(store: SentryStore, issue_ref: str) -> list[dict[str, Any]]:
    return store.activity(issue_ref)

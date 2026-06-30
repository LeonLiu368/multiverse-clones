from __future__ import annotations

import copy
from typing import Any

from .state import SentryStore


def list_issue_events(store: SentryStore, issue_ref: str) -> list[dict[str, Any]]:
    return [_shape_event(item) for item in store.events_for_issue(issue_ref)]


def latest_event(store: SentryStore, issue_ref: str) -> dict[str, Any] | None:
    event = store.latest_event(issue_ref)
    return _shape_event(event) if event else None


def get_event(store: SentryStore, project_slug: str, event_id: str) -> dict[str, Any] | None:
    event = store.event(event_id, project_slug)
    return _shape_event(event) if event else None


def stacktrace_for_issue(store: SentryStore, issue_ref: str) -> dict[str, Any] | None:
    event = latest_event(store, issue_ref)
    if not event:
        return None
    return {"event_id": event.get("id"), "stacktrace": copy.deepcopy(event.get("stacktrace", {}))}


def breadcrumbs_for_issue(store: SentryStore, issue_ref: str) -> dict[str, Any] | None:
    event = latest_event(store, issue_ref)
    if not event:
        return None
    return {"event_id": event.get("id"), "breadcrumbs": copy.deepcopy(event.get("breadcrumbs", []))}


def tags_for_issue(store: SentryStore, issue_ref: str) -> dict[str, Any] | None:
    issue = store.issue(issue_ref)
    if not issue:
        return None
    return {"issue_id": issue.get("id"), "shortId": issue.get("shortId"), "tags": copy.deepcopy(issue.get("tags", {}))}


def _shape_event(event: dict[str, Any]) -> dict[str, Any]:
    shaped = copy.deepcopy(event)
    shaped.setdefault("eventID", event.get("id"))
    shaped.setdefault("dateCreated", event.get("timestamp"))
    return shaped

from __future__ import annotations

import copy
from typing import Any

from .state import SentryStore


SORT_FIELDS = {
    "lastSeen": "lastSeen",
    "firstSeen": "firstSeen",
    "events": "count",
    "users": "userCount",
    # Real Sentry sort aliases (kept alongside the names above).
    "date": "lastSeen",
    "new": "firstSeen",
    "freq": "count",
    "user": "userCount",
}

# Sort fields that hold numeric values and must be compared numerically (not lexicographically).
_NUMERIC_SORT_FIELDS = {"count", "userCount"}


def list_project_issues(
    store: SentryStore,
    org_slug: str,
    project_slug: str,
    query: str | None = None,
    sort: str | None = None,
    stats_period: str | None = None,
) -> list[dict[str, Any]]:
    items = store.issues(org_slug, project_slug)
    return _shape_issues(_filter_issues(items, query), sort, stats_period)


def list_org_issues(
    store: SentryStore,
    org_slug: str,
    query: str | None = None,
    sort: str | None = None,
    stats_period: str | None = None,
) -> list[dict[str, Any]]:
    items = store.issues(org_slug)
    return _shape_issues(_filter_issues(items, query), sort, stats_period)


def get_issue(store: SentryStore, issue_ref: str) -> dict[str, Any] | None:
    issue = store.issue(issue_ref)
    return _shape_issue(issue) if issue else None


def update_issue(store: SentryStore, issue_ref: str, payload: dict[str, Any]) -> dict[str, Any]:
    changes = copy.deepcopy(payload)
    if changes.get("status") == "resolved" and "statusDetails" in changes:
        in_release = changes["statusDetails"].get("inRelease") if isinstance(changes["statusDetails"], dict) else None
        if in_release:
            changes["resolvedInRelease"] = in_release
    return _shape_issue(store.update_issue(issue_ref, changes))


def suspect_commits(store: SentryStore, issue_ref: str) -> list[dict[str, Any]]:
    issue = store.issue(issue_ref)
    if not issue:
        return []
    return copy.deepcopy(issue.get("suspectCommits") or [])


def assign_issue(store: SentryStore, issue_ref: str, *, team: str | None = None, user: str | None = None) -> dict[str, Any]:
    if team:
        assignee = {"type": "team", "slug": team, "name": team}
    elif user:
        assignee = {"type": "user", "email": user, "name": user}
    else:
        raise ValueError("team or user is required")
    return _shape_issue(store.assign_issue(issue_ref, assignee))


def resolve_issue(store: SentryStore, issue_ref: str, in_release: str | None = None) -> dict[str, Any]:
    return _shape_issue(store.set_status(issue_ref, "resolved", substatus="resolved", resolved_in_release=in_release))


def ignore_issue(store: SentryStore, issue_ref: str, reason: str | None = None) -> dict[str, Any]:
    return _shape_issue(store.set_status(issue_ref, "ignored", substatus="until_escalating", ignore_reason=reason))


def reopen_issue(store: SentryStore, issue_ref: str) -> dict[str, Any]:
    return _shape_issue(store.set_status(issue_ref, "unresolved", substatus="ongoing"))


def mark_regressed(store: SentryStore, issue_ref: str) -> dict[str, Any]:
    return _shape_issue(store.update_issue(issue_ref, {"status": "unresolved", "substatus": "regressed", "regressed": True}))


def _shape_issues(items: list[dict[str, Any]], sort: str | None, stats_period: str | None) -> list[dict[str, Any]]:
    field = SORT_FIELDS.get(sort or "lastSeen", "lastSeen")
    shaped = [_shape_issue(item, stats_period=stats_period) for item in items]
    if field in _NUMERIC_SORT_FIELDS:
        return sorted(shaped, key=lambda item: _as_number(item.get(field)), reverse=True)
    return sorted(shaped, key=lambda item: item.get(field) or "", reverse=True)


def _as_number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _shape_issue(issue: dict[str, Any], stats_period: str | None = None) -> dict[str, Any]:
    shaped = copy.deepcopy(issue)
    shaped.setdefault("metadata", {"title": issue.get("title")})
    shaped.setdefault("logger", issue.get("culprit"))
    shaped.setdefault("permalink", f"/organizations/{issue.get('project_slug')}/issues/{issue.get('id')}/")
    shaped.setdefault("stats", {"period": stats_period or "24h", "count": issue.get("count", 0), "userCount": issue.get("userCount", 0)})
    return shaped


def _filter_issues(items: list[dict[str, Any]], query: str | None) -> list[dict[str, Any]]:
    # Match real Sentry: when the caller omits ``query`` entirely, default to
    # ``is:unresolved`` so "the open issues" excludes resolved/ignored ones.
    # An explicitly-passed query (even an empty string, used to broaden to all
    # issues) is honored as-is.
    if query is None:
        query = "is:unresolved"
    if not query:
        return list(items)
    terms = [term.strip() for term in query.split() if term.strip()]
    filtered = list(items)
    for term in terms:
        key, sep, value = term.partition(":")
        if not sep:
            continue
        filtered = [issue for issue in filtered if _matches_term(issue, key, value)]
    return filtered


def _matches_term(issue: dict[str, Any], key: str, value: str) -> bool:
    status = str(issue.get("status", ""))
    substatus = str(issue.get("substatus", ""))
    if key == "is":
        if value == "unresolved":
            return status == "unresolved"
        if value == "resolved":
            return status == "resolved"
        if value == "ignored":
            return status == "ignored"
        if value == "regressed":
            return bool(issue.get("regressed")) or substatus == "regressed"
        if value == "for_review":
            return substatus == "for_review" or bool(issue.get("forReview"))
        if value == "escalating":
            return substatus == "escalating" or bool(issue.get("escalating"))
        return False
    if key == "level":
        return str(issue.get("level")) == value
    if key == "environment":
        return str(issue.get("environment") or issue.get("tags", {}).get("environment")) == value
    if key == "release":
        return str(issue.get("tags", {}).get("release")) == value
    if key == "assigned":
        if value == "none":
            return not issue.get("assignedTo")
        assigned = issue.get("assignedTo") or {}
        return value in {str(assigned.get("slug")), str(assigned.get("email")), str(assigned.get("name"))}
    if key == "project":
        return str(issue.get("project_slug")) == value
    return str(issue.get("tags", {}).get(key)) == value

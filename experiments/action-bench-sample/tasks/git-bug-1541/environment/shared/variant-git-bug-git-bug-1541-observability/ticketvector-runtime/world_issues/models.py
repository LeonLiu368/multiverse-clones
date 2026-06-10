from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any


def now_iso() -> str:
    return datetime(2026, 6, 4, 12, 0, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def copy_json(value: Any) -> Any:
    return deepcopy(value)


def issue_url(base_url: str, workspace: str, project_key: str, identifier: str) -> str:
    root = base_url.rstrip("/") if base_url else "https://plane.local"
    return f"{root}/{workspace}/projects/{project_key}/issues/{identifier}"


def minimal_issue(issue: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": issue["id"],
        "identifier": issue["identifier"],
        "title": issue["title"],
        "state": issue["state"],
        "priority": issue.get("priority"),
        "assignees": issue.get("assignees", []),
        "labels": issue.get("labels", []),
        "updated_at": issue.get("updated_at"),
        "url": issue.get("url"),
    }


def mutation_receipt(
    action: str,
    target: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    *,
    dry_run: bool = False,
    warnings: list[str] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    receipt = {
        "ok": True,
        "action": action,
        "target": target,
        "before": before,
        "after": after,
        "warnings": warnings or [],
        "dry_run": dry_run,
    }
    if extra:
        receipt.update(extra)
    return receipt


from __future__ import annotations

import json
import sys
from typing import Any

from .errors import redact


def filter_fields(value: Any, fields: list[str] | None) -> Any:
    if not fields:
        return value
    if isinstance(value, list):
        return [filter_fields(item, fields) for item in value]
    if isinstance(value, dict):
        return {field: value.get(field) for field in fields if field in value}
    return value


def emit(value: Any, *, fmt: str = "plain", fields: list[str] | None = None, quiet: bool = False) -> None:
    if quiet:
        return
    value = filter_fields(value, fields)
    if fmt == "json":
        print(json.dumps(redact(value), sort_keys=True, separators=(",", ":")))
    elif fmt == "markdown":
        print(to_markdown(value))
    else:
        print(to_plain(value))


def emit_error(message: str, *, fmt: str = "plain", code: int = 1, detail: Any = None) -> None:
    value = {"ok": False, "error": redact(message), "exit_code": code, "detail": redact(detail)}
    if fmt == "json":
        print(json.dumps(value, sort_keys=True, separators=(",", ":")), file=sys.stderr)
    else:
        print(f"error: {redact(message)}", file=sys.stderr)


def to_plain(value: Any) -> str:
    if isinstance(value, list):
        return "\n".join(_one_line(item) for item in value)
    if isinstance(value, dict):
        if "results" in value:
            return to_plain(value["results"])
        if "identifier" in value and "title" in value:
            return _issue_plain(value)
        if value.get("ok") is True and "action" in value:
            dry = " dry-run" if value.get("dry_run") else ""
            return f"{value['action']} {value['target']} ok{dry}"
        return "\n".join(f"{key}: {_simple(val)}" for key, val in value.items())
    return str(value)


def _one_line(item: Any) -> str:
    if isinstance(item, dict):
        if "identifier" in item:
            assignees = ",".join(user["handle"] for user in item.get("assignees", [])) or "unassigned"
            labels = ",".join(label["name"] for label in item.get("labels", []))
            return (
                f"{item['identifier']} [{item.get('state', {}).get('name', '-')}] "
                f"{item.get('priority', '-')}: {item.get('title', '')} "
                f"({assignees}{'; ' + labels if labels else ''})"
            )
        if "key" in item and "name" in item:
            return f"{item['key']} {item['name']}"
        if "name" in item:
            return item["name"]
        if "body" in item and "author" in item:
            return f"{item['author']['handle']}: {item['body']}"
    return _simple(item)


def _issue_plain(issue: dict[str, Any]) -> str:
    assignees = ", ".join(user["handle"] for user in issue.get("assignees", [])) or "unassigned"
    labels = ", ".join(label["name"] for label in issue.get("labels", [])) or "none"
    return "\n".join(
        [
            f"{issue['identifier']}: {issue['title']}",
            f"State: {issue['state']['name']} | Priority: {issue.get('priority')} | Assignee: {assignees}",
            f"Labels: {labels}",
            "",
            issue.get("description", ""),
        ]
    )


def to_markdown(value: Any) -> str:
    if isinstance(value, dict) and "identifier" in value:
        assignees = ", ".join(user["handle"] for user in value.get("assignees", [])) or "unassigned"
        labels = ", ".join(label["name"] for label in value.get("labels", [])) or "none"
        return "\n".join(
            [
                f"# {value['identifier']}: {value['title']}",
                "",
                f"- State: {value['state']['name']}",
                f"- Assignee: {assignees}",
                f"- Labels: {labels}",
                f"- Priority: {value.get('priority')}",
                "",
                value.get("description", ""),
            ]
        )
    return to_plain(value)


def _simple(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True)
    return str(value)


from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def snapshot_dir(cwd: str | Path = ".") -> Path:
    return Path(cwd) / ".ticketvector" / "snapshots"


def save_snapshot(name: str, data: dict[str, Any], *, cwd: str | Path = ".") -> Path:
    directory = snapshot_dir(cwd)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{name}.json"
    path.write_text(json.dumps(with_receipts(data, cwd=cwd), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def load_snapshot(name: str, *, cwd: str | Path = ".") -> dict[str, Any]:
    return json.loads((snapshot_dir(cwd) / f"{name}.json").read_text(encoding="utf-8"))


def snapshot_exists(name: str, *, cwd: str | Path = ".") -> bool:
    return (snapshot_dir(cwd) / f"{name}.json").exists()


def diff_snapshots(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    after = with_receipts(after)
    before_issues = {issue["identifier"]: issue for issue in before.get("issues", [])}
    after_issues = {issue["identifier"]: issue for issue in after.get("issues", [])}
    changes = []
    for identifier in sorted(set(before_issues) | set(after_issues)):
        old = before_issues.get(identifier)
        new = after_issues.get(identifier)
        if old is None:
            changes.append({"type": "issue.added", "issue": identifier, "after": new})
            continue
        if new is None:
            changes.append({"type": "issue.deleted", "issue": identifier, "before": old})
            continue
        fields = {}
        for field in ["title", "description", "priority", "state", "assignees", "labels", "cycle", "module"]:
            if old.get(field) != new.get(field):
                fields[field] = {"before": old.get(field), "after": new.get(field)}
        if fields:
            changes.append({"type": "issue.changed", "issue": identifier, "fields": fields})
    before_comments = sum(len(items) for items in before.get("comments", {}).values())
    after_comments = sum(len(items) for items in after.get("comments", {}).values())
    before_links = sum(len(items) for items in before.get("links", {}).values())
    after_links = sum(len(items) for items in after.get("links", {}).values())
    before_receipts = len(before.get("receipts", []))
    after_receipts = len(after.get("receipts", []))
    return {
        "ok": True,
        "changes": changes,
        "comment_delta": after_comments - before_comments,
        "link_delta": after_links - before_links,
        "receipt_delta": after_receipts - before_receipts,
        "receipts": after.get("receipts", []),
    }


def receipt_dir(cwd: str | Path = ".") -> Path:
    return Path(cwd) / ".ticketvector" / "receipts"


def save_receipt(receipt: dict[str, Any], *, cwd: str | Path = ".") -> Path:
    directory = receipt_dir(cwd)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{receipt.get('target', 'receipt')}-{receipt.get('action', 'action')}.json"
    target.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def load_receipts(*, cwd: str | Path = ".") -> list[dict[str, Any]]:
    directory = receipt_dir(cwd)
    if not directory.exists():
        return []
    receipts = []
    for path in sorted(directory.glob("*.json")):
        receipts.append(json.loads(path.read_text(encoding="utf-8")))
    return receipts


def clear_receipts(*, cwd: str | Path = ".") -> None:
    directory = receipt_dir(cwd)
    if not directory.exists():
        return
    for path in directory.glob("*.json"):
        path.unlink()


def with_receipts(data: dict[str, Any], *, cwd: str | Path = ".") -> dict[str, Any]:
    copy = dict(data)
    copy["receipts"] = load_receipts(cwd=cwd)
    return copy

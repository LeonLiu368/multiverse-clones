from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_MANIFEST = Path(".ticketvector/manifests/payments-world-v1.json")


def manifest_path(path: str | Path | None = None, *, cwd: str | Path = ".") -> Path:
    if path is None:
        return Path(cwd) / DEFAULT_MANIFEST
    name = Path(path).stem
    if name in {"payments-world", "payments"}:
        return Path(cwd) / DEFAULT_MANIFEST
    return Path(cwd) / ".ticketvector" / "manifests" / f"{name}-v1.json"


def read_manifest(path: str | Path | None = None, *, cwd: str | Path = ".") -> dict[str, Any]:
    target = manifest_path(path, cwd=cwd)
    if not target.exists():
        return {}
    return json.loads(target.read_text(encoding="utf-8"))


def write_manifest(data: dict[str, Any], path: str | Path | None = None, *, cwd: str | Path = ".") -> Path:
    target = manifest_path(path, cwd=cwd)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def issue_mapping(manifest: dict[str, Any], fixture_id: str) -> dict[str, Any] | None:
    issues = manifest.get("issues", {})
    if isinstance(issues, dict):
        value = issues.get(fixture_id)
        return value if isinstance(value, dict) else None
    return None


def resolve_issue_ref(value: str, *, cwd: str | Path = ".") -> str:
    mapping = issue_mapping(read_manifest(cwd=cwd), value)
    if not mapping:
        return value
    return str(mapping.get("actual_identifier") or mapping.get("actual_id") or value)


def upsert_issue_mapping(
    manifest: dict[str, Any],
    *,
    fixture_id: str,
    actual_id: str,
    actual_identifier: str,
    title: str,
) -> None:
    manifest.setdefault("issues", {})[fixture_id] = {
        "actual_id": actual_id,
        "actual_identifier": actual_identifier,
        "title": title,
    }

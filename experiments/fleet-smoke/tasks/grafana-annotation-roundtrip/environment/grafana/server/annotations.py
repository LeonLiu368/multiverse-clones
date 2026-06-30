from __future__ import annotations

from typing import Any

from .state import GrafanaStore


def list_annotations(
    store: GrafanaStore,
    dashboard_uid: str | None = None,
    tags: list[str] | None = None,
) -> list[dict[str, Any]]:
    wanted_tags = {tag for tag in tags or [] if tag}
    results = []
    for annotation in store.annotations():
        if dashboard_uid and annotation.get("dashboardUID") != dashboard_uid and annotation.get("dashboard_uid") != dashboard_uid:
            continue
        ann_tags = set(annotation.get("tags") or [])
        if wanted_tags and not wanted_tags.issubset(ann_tags):
            continue
        results.append(annotation)
    return results


def create_annotation(store: GrafanaStore, payload: dict[str, Any]) -> dict[str, Any]:
    dashboard_uid = payload.get("dashboardUID") or payload.get("dashboard_uid") or payload.get("dashboard")
    if not dashboard_uid:
        raise ValueError("dashboard UID is required")
    if not payload.get("text"):
        raise ValueError("annotation text is required")
    annotation = {
        "dashboardUID": dashboard_uid,
        "panelId": payload.get("panelId") or payload.get("panel_id"),
        "text": payload["text"],
        "tags": payload.get("tags") or [],
    }
    if annotation["panelId"] is None:
        annotation.pop("panelId")
    return store.add_annotation(annotation)

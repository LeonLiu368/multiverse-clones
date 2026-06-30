from __future__ import annotations

from typing import Any

from . import links
from .state import GaugeStore


def search_dashboards(store: GaugeStore, query: str | None = None, type_filter: str | None = None) -> list[dict[str, Any]]:
    if type_filter and type_filter != "dash-db":
        return []
    needle = (query or "").strip().lower()
    results = []
    for dashboard in store.dashboards():
        haystack = " ".join(
            [
                str(dashboard.get("uid", "")),
                str(dashboard.get("title", "")),
                str(dashboard.get("folder", "")),
                " ".join(str(tag) for tag in dashboard.get("tags", [])),
            ]
        ).lower()
        if needle and needle not in haystack:
            continue
        results.append(
            {
                "id": dashboard.get("id"),
                "uid": dashboard["uid"],
                "title": dashboard.get("title", dashboard["uid"]),
                "type": "dash-db",
                "folderTitle": dashboard.get("folder", "General"),
                "tags": dashboard.get("tags", []),
                "url": links.dashboard_link("", dashboard)["path"],
            }
        )
    return results


def dashboard_response(store: GaugeStore, uid: str) -> dict[str, Any] | None:
    dashboard = store.dashboard(uid)
    if not dashboard:
        return None
    return {
        "dashboard": {
            "uid": dashboard["uid"],
            "title": dashboard.get("title", dashboard["uid"]),
            "tags": dashboard.get("tags", []),
            "panels": dashboard.get("panels", []),
            "variables": dashboard.get("variables", []),
            "templating": {"list": dashboard.get("variables", [])},
            "schemaVersion": 39,
            "version": 1,
        },
        "meta": {
            "type": "db",
            "canSave": False,
            "canEdit": False,
            "folderTitle": dashboard.get("folder", "General"),
            "url": links.dashboard_link("", dashboard)["path"],
        },
    }


def dashboard_summary(store: GaugeStore, uid: str) -> dict[str, Any] | None:
    dashboard = store.dashboard(uid)
    if not dashboard:
        return None
    panels = dashboard.get("panels", [])
    return {
        "uid": dashboard["uid"],
        "title": dashboard.get("title", dashboard["uid"]),
        "folder": dashboard.get("folder", "General"),
        "tags": dashboard.get("tags", []),
        "panel_count": len(panels),
        "variables": dashboard.get("variables", []),
        "panels": [
            {
                "id": panel.get("id"),
                "title": panel.get("title"),
                "type": panel.get("type"),
                "datasource_uid": panel.get("datasource_uid"),
                "query": panel.get("query"),
            }
            for panel in panels
        ],
    }


def panel_queries(store: GaugeStore, uid: str) -> list[dict[str, Any]] | None:
    dashboard = store.dashboard(uid)
    if not dashboard:
        return None
    return [
        {
            "dashboard_uid": uid,
            "panel_id": panel.get("id"),
            "panel_title": panel.get("title"),
            "datasource_uid": panel.get("datasource_uid"),
            "query": panel.get("query"),
        }
        for panel in dashboard.get("panels", [])
    ]

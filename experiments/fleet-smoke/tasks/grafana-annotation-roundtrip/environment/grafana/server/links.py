from __future__ import annotations

import json
import re
import urllib.parse
from typing import Any


def slug(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return text or "dashboard"


def dashboard_link(base_url: str, dashboard: dict[str, Any]) -> dict[str, str]:
    uid = str(dashboard["uid"])
    path = f"/d/{uid}/{slug(str(dashboard.get('title') or uid))}"
    return {"url": base_url.rstrip("/") + path, "path": path}


def panel_link(
    base_url: str,
    dashboard: dict[str, Any],
    panel_id: int,
    from_range: str | None = None,
    to_range: str | None = None,
) -> dict[str, str]:
    item = dashboard_link(base_url, dashboard)
    query = {"viewPanel": str(panel_id)}
    if from_range:
        query["from"] = from_range
    if to_range:
        query["to"] = to_range
    path = item["path"] + "?" + urllib.parse.urlencode(query)
    return {"url": base_url.rstrip("/") + path, "path": path}


def explore_link(base_url: str, datasource_uid: str, query: str) -> dict[str, str]:
    left = json.dumps({"datasource": datasource_uid, "queries": [{"expr": query}], "range": {"from": "now-1h", "to": "now"}})
    path = "/explore?" + urllib.parse.urlencode({"left": left})
    return {"url": base_url.rstrip("/") + path, "path": path}

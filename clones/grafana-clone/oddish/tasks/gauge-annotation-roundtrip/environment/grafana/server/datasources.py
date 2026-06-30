from __future__ import annotations

from typing import Any

from .state import GrafanaStore


SUPPORTED_TYPES = {"prometheus", "loki"}


def datasource_payload(datasource: dict[str, Any]) -> dict[str, Any]:
    item = dict(datasource)
    item.setdefault("access", "proxy")
    item.setdefault("url", "")
    item.setdefault("isDefault", False)
    item.setdefault("readOnly", True)
    item.setdefault("jsonData", {})
    return item


def list_datasources(store: GrafanaStore) -> list[dict[str, Any]]:
    return [datasource_payload(item) for item in store.datasources()]


def get_datasource(store: GrafanaStore, uid: str) -> dict[str, Any] | None:
    item = store.datasource(uid)
    return datasource_payload(item) if item else None


def health(datasource: dict[str, Any]) -> dict[str, Any]:
    mode = datasource.get("mode", "embedded")
    if mode != "embedded":
        return {
            "uid": datasource.get("uid"),
            "status": "unsupported",
            "message": "external HTTP datasources are not implemented in Grafana v1",
        }
    return {
        "uid": datasource.get("uid"),
        "status": datasource.get("health", "ok"),
        "message": f"{datasource.get('type', 'datasource')} datasource is {datasource.get('health', 'ok')}",
    }

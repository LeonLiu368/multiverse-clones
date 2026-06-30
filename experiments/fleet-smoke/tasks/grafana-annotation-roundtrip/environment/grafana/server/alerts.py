from __future__ import annotations

from typing import Any

from .state import GrafanaStore


def list_rules(store: GrafanaStore, state_filter: str | None = None) -> list[dict[str, Any]]:
    rules = store.alerts()
    if state_filter:
        rules = [rule for rule in rules if rule.get("state") == state_filter]
    return [rule_payload(rule) for rule in rules]


def get_rule(store: GrafanaStore, uid: str) -> dict[str, Any] | None:
    rule = store.alert(uid)
    return rule_payload(rule) if rule else None


def list_instances(store: GrafanaStore, state_filter: str | None = None) -> list[dict[str, Any]]:
    return [instance_payload(item) for item in store.alert_instances(state_filter)]


def state_history(store: GrafanaStore, rule_uid: str) -> list[dict[str, Any]]:
    return store.alert_state_history(rule_uid)


def rule_payload(rule: dict[str, Any]) -> dict[str, Any]:
    item = dict(rule)
    item.setdefault("folderUID", item.get("dashboard_uid"))
    item.setdefault("condition", "A")
    item.setdefault("data", [{"refId": "A", "query": item.get("query")}])
    item.setdefault("annotations", {})
    return item


def instance_payload(instance: dict[str, Any]) -> dict[str, Any]:
    item = dict(instance)
    item.setdefault("labels", {})
    item.setdefault("annotations", {})
    return item

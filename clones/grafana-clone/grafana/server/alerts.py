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


def prometheus_rules(store: GrafanaStore, state_filter: str | None = None) -> dict[str, Any]:
    """The Prometheus-compatible alerting shape served by real Grafana at
    /api/prometheus/grafana/api/v1/rules: {status, data:{groups:[{name,file,rules:[...]}]}}."""
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for rule in store.alerts():
        if state_filter and rule.get("state") != state_filter:
            continue
        uid = rule.get("uid") or rule.get("id")
        folder = str(rule.get("folderUID") or rule.get("dashboard_uid") or "general")
        group = str(rule.get("ruleGroup") or rule.get("rule_group") or "default")
        alerts_for_rule = [
            {
                "labels": inst.get("labels", {}),
                "annotations": inst.get("annotations", {}),
                "state": inst.get("state", rule.get("state")),
                "activeAt": inst.get("activeAt") or inst.get("active_at"),
            }
            for inst in store.alert_instances(None)
            if (inst.get("rule_uid") or inst.get("ruleUID")) == uid
        ]
        groups.setdefault((group, folder), []).append(
            {
                "name": rule.get("title") or rule.get("name") or str(uid),
                "state": rule.get("state"),
                "labels": rule.get("labels", {}),
                "annotations": rule.get("annotations", {}),
                "alerts": alerts_for_rule,
            }
        )
    return {
        "status": "success",
        "data": {
            "groups": [
                {"name": name, "file": folder, "rules": rules}
                for (name, folder), rules in groups.items()
            ]
        },
    }

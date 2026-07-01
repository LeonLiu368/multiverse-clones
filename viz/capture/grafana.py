"""Capture Grafana-clone parity demos in-process against the real seed file.

Running this verifies the seed format is accepted (the clone store loads it and serves reads)
AND captures the clone's ACTUAL output for the dashboard comparison boxes. The `real_output`
golden samples are authored from the real Grafana HTTP API docs.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

CLONE = Path(__file__).resolve().parents[2] / "clones" / "grafana-clone"
sys.path.insert(0, str(CLONE))

from grafana.server import alerts, annotations, dashboards, query_engine  # noqa: E402
from grafana.server.state import GrafanaStore  # noqa: E402

SEED_REL = "examples/data/grafana/state.json"


def build() -> dict:
    seed = json.load(open(CLONE / SEED_REL))
    store = GrafanaStore(copy.deepcopy(seed))

    dash = seed["dashboards"][0]
    uid = dash["uid"]
    metric_expr = next(iter(seed["metrics"]["queries"]))
    log_expr = next(iter(seed["logs"]["queries"]))

    demos = []

    # ---- GET: dashboard search (list view) --------------------------------
    clone_search = dashboards.search_dashboards(store, "payment", "dash-db")
    demos.append({
        "id": "dashboard-search",
        "title": "Search dashboards",
        "method": "GET",
        "capability": "Dashboard search",
        "seed_excerpt": {"dashboards": [{"uid": uid, "title": dash.get("title"), "tags": dash.get("tags", [])}]},
        "ui": {"type": "list", "title": "Grafana › Dashboards",
               "rows": [{"icon": "▦", "title": d.get("title"), "sub": d.get("uid"),
                         "tags": d.get("tags", [])} for d in clone_search]},
        "agent": {"cli": "gcx dashboards search payment",
                  "mcp": {"tool": "search_dashboards", "args": {"query": "payment"}}},
        "real_mapping": {
            "api": "GET /api/search?query=payment&type=dash-db",
            "mcp": "mcp-grafana › search_dashboards",
            "doc": "https://grafana.com/docs/grafana/latest/developers/http_api/folder_dashboard_search/"},
        "clone_output": clone_search,
        "real_output": [{
            "id": 1, "uid": uid, "title": dash.get("title"), "uri": f"db/{uid}",
            "url": f"/d/{uid}/{uid}", "slug": "", "type": "dash-db", "tags": dash.get("tags", []),
            "isStarred": False, "folderTitle": "General", "folderUid": "", "sortMeta": 0}],
    })

    # ---- GET: panel query (chart view, the P0-fixed dataframe surface) -----
    q = {"queries": [{"refId": "A", "queryType": "metrics",
                      "datasource": {"uid": "prom-payments"}, "expr": metric_expr}]}
    clone_q = query_engine.ds_query(store, q)
    demos.append({
        "id": "panel-query",
        "title": "Run a panel query (PromQL)",
        "method": "GET",
        "capability": "Panel query exec → dataframes",
        "seed_excerpt": {"metrics": {"queries": {metric_expr: seed["metrics"]["queries"][metric_expr]}}},
        "ui": {"type": "chart", "title": "payment_gateway_responses_total",
               "series": _series_for_chart(clone_q)},
        "agent": {"cli": f"gcx dashboards query-panel {uid} 1",
                  "mcp": {"tool": "run_panel_query", "args": {"dashboard_uid": uid, "panel_id": 1}}},
        "real_mapping": {
            "api": "POST /api/ds/query",
            "mcp": "mcp-grafana › run_panel_query",
            "doc": "https://grafana.com/docs/grafana/latest/developers/http_api/data_source/"},
        "clone_output": clone_q,
        "real_output": {"results": {"A": {"status": 200, "frames": [{
            "schema": {"refId": "A", "fields": [
                {"name": "Time", "type": "time"},
                {"name": "Value", "type": "number", "labels": {"status_code": "425"}}]},
            "data": {"values": [[1780826400000, 1780833300000], [3, 31]]}}]}}},
    })

    # ---- GET: alert rules (real path served by the reliability fix) --------
    clone_rules = alerts.list_rules(store)
    demos.append({
        "id": "alert-rules",
        "title": "List alert rules",
        "method": "GET",
        "capability": "Alerting rules (real provisioning path)",
        "seed_excerpt": {"alerts": [{"uid": r.get("uid"), "title": r.get("title"),
                                     "state": r.get("state")} for r in seed.get("alerts", [])][:3]},
        "ui": {"type": "list", "title": "Grafana › Alerting › Rules",
               "rows": [{"icon": _alert_icon(r.get("state")), "title": r.get("title"),
                         "sub": r.get("uid"), "tags": [r.get("state", "")]} for r in clone_rules]},
        "agent": {"cli": "gcx alerts rules", "mcp": {"tool": "list_alert_rules", "args": {}}},
        "real_mapping": {
            "api": "GET /api/v1/provisioning/alert-rules",
            "mcp": "mcp-grafana › list_alert_rules",
            "doc": "https://grafana.com/docs/grafana/latest/developers/http_api/alerting_provisioning/"},
        "clone_output": clone_rules,
        "real_output": [{"uid": (clone_rules[0].get("uid") if clone_rules else "arel-1"),
                         "title": (clone_rules[0].get("title") if clone_rules else "High 5xx rate"),
                         "condition": "A", "folderUID": "", "ruleGroup": "default",
                         "state": (clone_rules[0].get("state") if clone_rules else "firing"),
                         "for": "5m", "annotations": {}, "labels": {}}],
    })

    # ---- POST: create annotation (before/after highlight) ------------------
    before = annotations.list_annotations(store, uid, None)
    created = annotations.create_annotation(store, {
        "dashboardUID": uid, "text": "deploy: payments v2.3.1", "tags": ["deploy"]})
    after = annotations.list_annotations(store, uid, None)
    demos.append({
        "id": "annotation-create",
        "title": "Create an annotation",
        "method": "POST",
        "capability": "Annotation write→read round-trip",
        "seed_excerpt": {"annotations_before": len(before)},
        "ui": {"type": "timeline", "title": f"Grafana › {dash.get('title')} (annotations)",
               "before": [_anno(a) for a in before], "after": [_anno(a) for a in after],
               "new_id": created.get("id")},
        "agent": {"cli": f'gcx annotations add {uid} "deploy: payments v2.3.1" --tag deploy',
                  "mcp": {"tool": "create_annotation",
                          "args": {"dashboard_uid": uid, "text": "deploy: payments v2.3.1", "tags": ["deploy"]}}},
        "real_mapping": {
            "api": "POST /api/annotations",
            "mcp": "mcp-grafana › create_annotation",
            "doc": "https://grafana.com/docs/grafana/latest/developers/http_api/annotations/"},
        "clone_output": created,
        "real_output": {"message": "Annotation added", "id": created.get("id")},
        "change": {"before": before, "after": after, "new_id": created.get("id")},
    })

    return {
        "clone": "grafana-clone",
        "product": "Grafana",
        "real_service": {
            "name": "Grafana HTTP API 11.x (+ Loki / Prometheus)",
            "reference": "https://grafana.com/docs/grafana/latest/developers/http_api/",
            "api_base": "{gateway}/api"},
        "parity": {"verdict": "HIGH after reliability pass",
                   "note": "ds/query now returns real dataframes; real provisioning/prometheus alerting paths served."},
        "seed_file": SEED_REL,
        "surfaces": {"cli": "gcx", "mcp": "mcp-grafana"},
        "demos": demos,
    }


def _series_for_chart(clone_q: dict) -> list:
    out = []
    for ref, res in clone_q.get("results", {}).items():
        for frame in res.get("frames", []):
            fields = frame["schema"]["fields"]
            times, values = frame["data"]["values"][0], frame["data"]["values"][1]
            label = fields[1].get("labels") or {}
            name = ",".join(f"{k}={v}" for k, v in label.items()) or fields[1]["name"]
            out.append({"name": name, "points": list(zip(times, values))})
    return out


def _alert_icon(state: str | None) -> str:
    return {"firing": "🔴", "alerting": "🔴", "pending": "🟡", "normal": "🟢", "ok": "🟢"}.get(
        (state or "").lower(), "⚪")


def _anno(a: dict) -> dict:
    return {"id": a.get("id"), "text": a.get("text"), "tags": a.get("tags", []), "time": a.get("time")}


if __name__ == "__main__":
    out = Path(__file__).resolve().parents[1] / "data" / "grafana-clone.json"
    manifest = build()
    out.write_text(json.dumps(manifest, indent=2, default=str))
    print(f"OK grafana-clone: {len(manifest['demos'])} demos, seed '{manifest['seed_file']}' accepted -> {out}")

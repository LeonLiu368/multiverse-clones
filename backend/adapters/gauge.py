"""gauge clone seed viewer — a Grafana/Loki-shaped state.json: datasources, dashboards (panels with
LogQL/PromQL exprs), and `logs.queries` keyed by a LogQL selector → log lines. Read-only."""
from __future__ import annotations

import json
from typing import Any

from adapters.fileseed import FileSeedAdapter


class GaugeAdapter(FileSeedAdapter):
    id = "gauge"
    display_name = "Grafana"
    status = "active"
    ui_module = "gauge"
    sample_files = ("gauge.state.json",)
    # multiverse-clones renamed this clone gauge → grafana-clone: image `grafana-service`, state
    # baked at /srv/grafana/state.json (Dockerfile.prod-v1, ENV GRAFANA_STATE_FILE). The state.json
    # shape (logs.queries / metrics.queries / datasources / dashboards) is unchanged. Older gauge-*
    # names/paths are kept for back-compat.
    image_substrings = ("grafana-service", "grafana-clone", "gauge-gateway", "gauge-service", "gauge-seed")
    # prod-v1 bakes /srv/grafana/state.json; the empty image mounts /data/grafana/state.json; the
    # runtime mutable copy is /var/lib/grafana/state.json. Older gauge-* paths kept for back-compat.
    image_state_paths = ("/srv/grafana/state.json", "/data/grafana/state.json",
                         "/var/lib/grafana/state.json", "/data/gauge/state.json",
                         "/var/lib/gauge/state.json")

    def _norm_lines(self, val: Any) -> list[dict]:
        """A LogQL query value -> a flat list of {ts, labels, line}. The seed varies: the sample
        stores a plain list, the real corpus stores {"entries": [...]}, and raw Loki uses
        {"values": [[ts, line], ...]}."""
        items = val if isinstance(val, list) else None
        if items is None and isinstance(val, dict):
            for k in ("entries", "values", "lines", "results", "data"):
                if isinstance(val.get(k), list):
                    items = val[k]
                    break
        out: list[dict] = []
        for it in items or []:
            if isinstance(it, dict):
                out.append({"ts": it.get("ts") or it.get("timestamp") or "",
                            "labels": it.get("labels") or {},
                            "line": it.get("line") or it.get("message") or ""})
            elif isinstance(it, (list, tuple)) and len(it) >= 2:
                out.append({"ts": str(it[0]), "labels": {}, "line": str(it[1])})
        return out

    def _norm_series(self, val: Any) -> list[dict]:
        """A PromQL query value -> a list of {metric, values:[[ts,val],...]}. Prometheus matrix shape
        is {"resultType":"matrix","series":[...]}; also accept a bare series list."""
        series = val.get("series") if isinstance(val, dict) else val
        out: list[dict] = []
        for s in series or []:
            if isinstance(s, dict):
                out.append({"metric": s.get("metric") or {}, "values": s.get("values") or []})
        return out

    def _merge(self, base: dict[str, Any], ov: dict[str, Any]) -> dict[str, Any]:
        """Overlay a second gauge state onto the base: union datasources/dashboards by uid, concat
        each overlay log stream (overlay lines tagged), and add overlay metric queries."""
        ds = {d.get("uid"): d for d in base["datasources"]}
        for d in ov["datasources"]:
            ds.setdefault(d.get("uid"), d)
        dash = {d.get("uid"): d for d in base["dashboards"]}
        for d in ov["dashboards"]:
            dash.setdefault(d.get("uid"), d)
        lq = {sel: list(lines) for sel, lines in base["log_queries"].items()}
        for sel, lines in ov["log_queries"].items():
            lq.setdefault(sel, []).extend({**ln, "origin": "overlay"} for ln in lines)
            lq[sel].sort(key=lambda x: x.get("ts", ""))
        mq = {**base["metric_queries"], **ov["metric_queries"]}
        return {
            **base, "datasources": list(ds.values()), "dashboards": list(dash.values()),
            "log_queries": lq, "metric_queries": mq,
            "stats": {"datasources": len(ds), "dashboards": len(dash), "log_streams": len(lq),
                      "log_lines": sum(len(v) for v in lq.values()), "metric_queries": len(mq)},
        }

    def _parse(self, raw: str, path: str) -> dict[str, Any]:
        d = json.loads(raw)
        raw_q = (d.get("logs") or {}).get("queries") or {}
        log_queries = {sel: self._norm_lines(val) for sel, val in raw_q.items()}
        raw_m = (d.get("metrics") or {}).get("queries") or {}
        metric_queries = {expr: self._norm_series(val) for expr, val in raw_m.items()}
        return {
            "meta": d.get("meta") or {},
            "datasources": d.get("datasources") or [],
            "dashboards": d.get("dashboards") or [],
            "alerts": d.get("alerts") or [],
            "log_queries": log_queries,
            "metric_queries": metric_queries,
            "stats": {
                "datasources": len(d.get("datasources") or []),
                "dashboards": len(d.get("dashboards") or []),
                "log_streams": len(log_queries),
                "log_lines": sum(len(v) for v in log_queries.values()),
                "metric_queries": len(metric_queries),
            },
        }

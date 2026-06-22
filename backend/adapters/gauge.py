"""gauge clone seed viewer — a Grafana/Loki-shaped state.json: datasources, dashboards (panels with
LogQL/PromQL exprs), and `logs.queries` keyed by a LogQL selector → log lines. Read-only."""
from __future__ import annotations

import json
from typing import Any

from adapters.fileseed import FileSeedAdapter


class GaugeAdapter(FileSeedAdapter):
    id = "gauge"
    display_name = "gauge"
    status = "active"
    ui_module = "gauge"
    sample_files = ("gauge.state.json",)

    def _parse(self, raw: str, path: str) -> dict[str, Any]:
        d = json.loads(raw)
        log_queries = (d.get("logs") or {}).get("queries") or {}
        metric_queries = (d.get("metrics") or {}).get("queries") or {}
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
            },
        }

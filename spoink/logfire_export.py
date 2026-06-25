"""Logfire telemetry export via the Query API (read-only) -> a declarative capture JSON.

Fourth source for spoink (the observability leg). Mirrors the others: a read-only client,
a fetch, an access/sufficiency report. Logfire holds ~276M records, so a raw "pull it all"
is infeasible AND redundant (few thousand distinct signatures). We capture two scoped views:

  - incident: every error+warn record in a tight window (default the 2h up to the cutoff),
    the gauge-bakeable log stream an agent investigates.
  - overview: the distinct error/exception signatures across the period with counts + a
    sample each -- a compact map of the whole period.

Read token only (Query API rejects write tokens). Token from env LOGFIRE_READ_TOKEN; the
region/host come from the token's `_us_`/`_eu_` segment. Never logged.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx

LEVEL_NAMES = {1: "trace", 5: "debug", 9: "info", 13: "warn", 17: "error", 21: "fatal"}


def _host(token: str) -> str:
    region = "eu" if "_eu_" in token else "us"
    return f"https://logfire-{region}.pydantic.dev/v2/query"


class LogfireError(Exception):
    pass


class LogfireClient:
    """Logfire Query API client: Bearer read token, SQL over `records`, {schema,data} responses."""

    def __init__(self, token: str, *, timeout: float = 120.0):
        self._url = _host(token)
        self._http = httpx.Client(
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "application/json"},
            timeout=timeout,
        )

    def close(self) -> None:
        self._http.close()

    def query(self, sql: str, min_ts: str, max_ts: Optional[str] = None, limit: int = 10000) -> List[Dict[str, Any]]:
        body: Dict[str, Any] = {"sql": sql, "min_timestamp": min_ts, "limit": limit}
        if max_ts:
            body["max_timestamp"] = max_ts
        r = self._http.post(self._url, json=body)
        if r.status_code != 200:
            raise LogfireError(f"{r.status_code}: {r.text[:200]}")
        return r.json().get("data", [])


def _lvl(n: Optional[int]) -> str:
    return LEVEL_NAMES.get(n or 0, str(n))


# --------------------------------------------------------------------------- fetch


INCIDENT_SQL = """
SELECT start_timestamp, service_name, level, message, span_name,
       is_exception, exception_type, exception_message, trace_id
FROM records WHERE level >= 13
ORDER BY start_timestamp
"""

OVERVIEW_SQL = """
SELECT message, service_name, count(*) AS n, max(level) AS level,
       min(start_timestamp) AS first_seen, max(start_timestamp) AS last_seen,
       max(exception_type) AS exception_type,
       max(exception_message) AS exception_message
FROM records WHERE level >= 17
GROUP BY message, service_name
ORDER BY n DESC
"""


def fetch(client: LogfireClient, incident_min: str, cutoff: str, period_min: str) -> Dict[str, Any]:
    incident = client.query(INCIDENT_SQL, incident_min, cutoff)
    overview = client.query(OVERVIEW_SQL, period_min, cutoff, limit=10000)
    for r in incident:
        r["level_name"] = _lvl(r.get("level"))
    for r in overview:
        r["level_name"] = _lvl(r.get("level"))
    return {
        "meta": {"workspace": "oddish", "source": "logfire",
                 "incident_window": [incident_min, cutoff], "overview_period": [period_min, cutoff],
                 "now": cutoff},
        "incident": incident,
        "overview": overview,
    }


# ------------------------------------------------------------------- gauge state.json


def _gts(ts: Optional[str]) -> str:
    """Logfire ISO (microsecond precision) -> gauge's canonical second-precision ISO Z,
    so gauge's time filter parses entry timestamps."""
    if not ts:
        return ""
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return ts


def to_gauge_state(data: Dict[str, Any]) -> Dict[str, Any]:
    """Map the Logfire capture into a gauge state.json (Loki-log shape gcx serves).

    Incident records -> per-service {service="..."} log streams; the overview signatures
    -> a {view="error-signatures"} stream. meta.now is anchored at the cutoff so a default
    `gcx logs query ... --since` surfaces the incident. Matches gauge validate_state.
    """
    cutoff = _gts(data["meta"]["now"])
    fixtures: Dict[str, Dict[str, Any]] = {}

    for r in data["incident"]:
        svc = r.get("service_name") or "unknown"
        sel = '{service="%s"}' % svc
        line = r.get("message") or r.get("span_name") or ""
        if r.get("is_exception") and r.get("exception_type"):
            line = f"{line} | {r['exception_type']}: {r.get('exception_message') or ''}".strip()
        fixtures.setdefault(sel, {"entries": []})["entries"].append({
            "ts": _gts(r["start_timestamp"]), "labels": {"service": svc, "level": r["level_name"]}, "line": line,
        })

    ov_entries = []
    for r in data["overview"]:
        line = f"[{r['n']}x] {r.get('service_name')} {r['level_name']}"
        if r.get("exception_type"):
            line += f" {r['exception_type']}"
        line += f": {r.get('message') or ''}"
        ov_entries.append({"ts": _gts(r.get("last_seen")) or cutoff,
                           "labels": {"service": "oddish", "view": "error-signatures", "level": r["level_name"]},
                           "line": line})
    if ov_entries:
        fixtures['{service="oddish",view="error-signatures"}'] = {"entries": ov_entries}

    for f in fixtures.values():
        f["entries"].sort(key=lambda e: e["ts"])

    return {
        "meta": {"workspace": "oddish", "now": cutoff},
        "users": [{"id": "u-agent", "login": "agent", "name": "Agent User"}],
        "datasources": [
            {"uid": "loki", "name": "oddish Loki", "type": "loki", "mode": "embedded", "health": "ok"},
            {"uid": "prom-default", "name": "oddish Prometheus", "type": "prometheus", "mode": "embedded", "health": "ok"},
        ],
        "dashboards": [{
            "uid": "dash-oddish", "title": "oddish incident", "folder": "Incidents",
            "tags": ["incident", "oddish"], "variables": [],
            "panels": [{"id": 1, "title": "oddish-backend logs", "type": "logs", "datasource_uid": "loki",
                        "targets": [{"datasource_uid": "loki", "expr": '{service="oddish-backend"}'}]}],
        }],
        "alerts": [], "metrics": {"queries": {}},
        "logs": {"queries": fixtures},
        "alert_instances": [], "alert_state_history": [], "annotations": [], "mutation_log": [],
    }


# --------------------------------------------------------------------------- report


def build_report(data: Dict[str, Any]) -> Dict[str, Any]:
    inc, ov = data["incident"], data["overview"]
    by_svc: Dict[str, int] = {}
    for r in inc:
        by_svc[r.get("service_name")] = by_svc.get(r.get("service_name"), 0) + 1
    return {
        "incident_records": len(inc),
        "incident_by_service": by_svc,
        "overview_signatures": len(ov),
        "incident_window": data["meta"]["incident_window"],
        "overview_period": data["meta"]["overview_period"],
        "sufficient": bool(inc and ov),
    }


# --------------------------------------------------------------------------- CLI


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="spoink.logfire_export", description="Read-only Logfire capture -> declarative JSON.")
    ap.add_argument("--until", default="2026-06-25T00:34:00Z", help="cutoff (ISO Z). default = 5:34 PT June 24")
    ap.add_argument("--incident-hours", type=float, default=2.0, help="incident window length before cutoff")
    ap.add_argument("--period-days", type=float, default=365.0, help="overview look-back before cutoff (capped by retention)")
    ap.add_argument("--out", default="logfire.json")
    ap.add_argument("--gauge-out", default=None, help="also write a gauge state.json (Loki-log shape)")
    ap.add_argument("--report", default=None)
    ap.add_argument("--token-env", default="LOGFIRE_READ_TOKEN")
    args = ap.parse_args(argv)

    token = os.environ.get(args.token_env)
    if not token:
        print(f"error: set {args.token_env} to a Logfire READ token (Query API rejects write tokens)", file=sys.stderr)
        return 2

    cutoff = datetime.fromisoformat(args.until.replace("Z", "+00:00")).astimezone(timezone.utc)
    fz = lambda d: d.strftime("%Y-%m-%dT%H:%M:%SZ")
    incident_min = fz(cutoff - timedelta(hours=args.incident_hours))
    period_min = fz(cutoff - timedelta(days=args.period_days))
    cutoff_s = fz(cutoff)

    client = LogfireClient(token)
    try:
        data = fetch(client, incident_min, cutoff_s, period_min)
        rep = build_report(data)
    finally:
        client.close()

    from pathlib import Path
    Path(args.out).write_text(json.dumps(data, indent=2))
    if args.gauge_out:
        Path(args.gauge_out).write_text(json.dumps(to_gauge_state(data), indent=2))
    print(json.dumps({"out": args.out, "gauge_out": args.gauge_out,
                      "incident_records": rep["incident_records"],
                      "overview_signatures": rep["overview_signatures"], "sufficient": rep["sufficient"]}))
    if args.report:
        md = args.report if args.report.endswith(".md") else args.report + ".md"
        L = ["# Logfire capture (oddish)", "",
             f"**Incident window:** {rep['incident_window'][0]} -> {rep['incident_window'][1]}  ",
             f"**Overview period:** {rep['overview_period'][0]} -> {rep['overview_period'][1]}  ",
             f"**Incident records:** {rep['incident_records']}  ",
             f"**Overview signatures:** {rep['overview_signatures']}  ", "", "## Incident by service", ""]
        L += [f"- {k}: {v}" for k, v in sorted(rep["incident_by_service"].items(), key=lambda x: -x[1])]
        Path(md).write_text("\n".join(L))
        Path(md[:-3] + ".json").write_text(json.dumps(rep, indent=2))
        print(f"report: {md}", file=sys.stderr)
    return 0 if rep["sufficient"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

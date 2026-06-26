"""Source registry — the single place that knows how to CAPTURE and SLICE each upstream,
wrapping spoink's existing export/slice modules (no logic duplicated here).

Each Source declares:
  * env_key   — the .env var holding its credential (presence is surfaced to the UI; the
                value is NEVER returned over the API).
  * params    — the capture-form schema (so the frontend renders the right inputs).
  * capture() — runs the real spoink fetch+write into a run dir, returns a small report.
  * slice()   — time-aligns a captured artifact to the incident cutoff T (where the module
                supports it); Logfire is captured as-of-T directly via its `until` param.
  * view_app  — the seed-dashboard app id used to display the produced overlay.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# Default incident moment (5:34 PT, 2026-06-24) — the canonical T this whole engine is built around.
DEFAULT_T = "2026-06-25T00:34:00Z"


class CaptureError(RuntimeError):
    pass


def _require_env(key: str) -> str:
    v = os.environ.get(key)
    if not v:
        raise CaptureError(f"missing credential: set {key} in .env")
    return v


@dataclass
class Param:
    name: str
    label: str
    kind: str = "text"          # text | datetime | select
    default: str = ""
    required: bool = False
    help: str = ""
    options: List[str] = field(default_factory=list)


@dataclass
class Source:
    id: str
    label: str
    env_key: str
    kind: str                   # artifact kind: slack-export | jira-state | logfire-json
    view_app: Optional[str]     # seed-dashboard app id (slack | jira | logfire | gauge)
    params: List[Param]
    can_slice: bool
    capture: Callable[[str, Dict[str, Any]], Dict[str, Any]]
    slice: Optional[Callable[[str, str, float], Dict[str, Any]]] = None
    # the artifact path (relative to the run dir) the capture writes
    artifact: str = ""

    def has_key(self) -> bool:
        return bool(os.environ.get(self.env_key))


# --------------------------------------------------------------------------- Slack
def _capture_slack(run_dir: str, params: Dict[str, Any]) -> Dict[str, Any]:
    from .. import slack_export as sx
    from ..slice import parse_cutoff
    token = _require_env("SLACK_USER_TOKEN")
    channels = [c.strip() for c in str(params.get("channels", "")).split(",") if c.strip()]
    if not channels:
        raise CaptureError("slack: --channels is required (comma-separated names)")
    since = params.get("since") or "90d"
    oldest = sx.parse_oldest(since)
    latest = None
    if params.get("latest"):
        latest = f"{parse_cutoff(params['latest'], params.get('tz') or None):.6f}"
    client = sx.SlackClient(token)
    try:
        data = sx.fetch_workspace(client, channels, oldest, latest)
        sample = data["channels"][0]["id"] if data["channels"] else None
        probe = sx.run_probe(client, sample)
        out = str(Path(run_dir) / "slack-export")
        counts = sx.write_export_dir(out, data)
        rep = sx.build_report(probe, counts, data, since=since, stalls=client.rate_limit_stalls)
    finally:
        client.close()
    return {"artifact": "slack-export", "counts": counts,
            "sufficient": rep.get("sufficient_for_task_gen"), "report": rep}


def _slice_slack(run_dir: str, artifact: str, cutoff: float) -> Dict[str, Any]:
    from ..slice import slice_export
    src = str(Path(run_dir) / artifact)
    out = str(Path(run_dir) / "slack-export@T")
    res = slice_export(src, out, cutoff)
    return {"artifact": "slack-export@T", "kept": res["kept"], "dropped": res["dropped"],
            "last_kept": res.get("last_kept"), "report": res}


# --------------------------------------------------------------------------- Linear
def _capture_linear(run_dir: str, params: Dict[str, Any]) -> Dict[str, Any]:
    from .. import linear_export as lx
    key = _require_env("LINEAR_API_KEY")
    client = lx.LinearClient(key)
    try:
        data = lx.fetch_workspace(client, params.get("team") or None)
        probe = lx.run_probe(client)
        state = lx.to_state(data)
        rep = lx.build_report(probe, state, data)
    finally:
        client.close()
    (Path(run_dir) / "state.json").write_text(json.dumps(state, indent=2, ensure_ascii=False))
    return {"artifact": "state.json", "team": rep.get("team"), "counts": rep.get("counts"),
            "sufficient": rep.get("sufficient_for_task_gen"), "report": rep}


def _slice_linear(run_dir: str, artifact: str, cutoff: float) -> Dict[str, Any]:
    from ..slice import slice_tracker
    state = json.loads((Path(run_dir) / artifact).read_text())
    res = slice_tracker(state, cutoff)
    (Path(run_dir) / "state@T.json").write_text(json.dumps(state, indent=2, ensure_ascii=False))
    return {"artifact": "state@T.json", **res}


# --------------------------------------------------------------------------- Logfire
def _capture_logfire(run_dir: str, params: Dict[str, Any]) -> Dict[str, Any]:
    from datetime import datetime, timedelta, timezone
    from .. import logfire_export as gx
    token = _require_env("LOGFIRE_READ_TOKEN")
    until = params.get("until") or DEFAULT_T
    incident_hours = float(params.get("incident_hours") or 2.0)
    period_days = float(params.get("period_days") or 365.0)
    cutoff = datetime.fromisoformat(until.replace("Z", "+00:00")).astimezone(timezone.utc)
    fz = lambda d: d.strftime("%Y-%m-%dT%H:%M:%SZ")
    client = gx.LogfireClient(token)
    try:
        data = gx.fetch(client, fz(cutoff - timedelta(hours=incident_hours)), fz(cutoff),
                        fz(cutoff - timedelta(days=period_days)))
        rep = gx.build_report(data)
    finally:
        client.close()
    (Path(run_dir) / "logfire.json").write_text(json.dumps(data, indent=2))
    (Path(run_dir) / "gauge-state.json").write_text(json.dumps(gx.to_gauge_state(data), indent=2))
    return {"artifact": "logfire.json", "gauge_artifact": "gauge-state.json",
            "incident_records": rep.get("incident_records"),
            "overview_signatures": rep.get("overview_signatures"),
            "sufficient": rep.get("sufficient"), "report": rep}


# --------------------------------------------------------------------------- registry
SOURCES: Dict[str, Source] = {
    "slack": Source(
        id="slack", label="Slack", env_key="SLACK_USER_TOKEN", kind="slack-export",
        view_app="slack", can_slice=True, artifact="slack-export",
        capture=_capture_slack, slice=_slice_slack,
        params=[
            Param("channels", "Channels", "text", required=True,
                  help="comma-separated names, e.g. team-code-infra,core-core"),
            Param("since", "Oldest (since)", "text", default="2y",
                  help="90d | 12h | all | YYYY-MM-DD"),
            Param("latest", "Newest (latest = T)", "datetime", default=DEFAULT_T,
                  help="newest bound; usually the incident T"),
            Param("tz", "TZ (for naive latest)", "text", default="",
                  help="e.g. -7 (PDT); leave blank for ISO/epoch"),
        ],
    ),
    "linear": Source(
        id="linear", label="Linear", env_key="LINEAR_API_KEY", kind="jira-state",
        view_app="jira", can_slice=True, artifact="state.json",
        capture=_capture_linear, slice=_slice_linear,
        params=[
            Param("team", "Team key", "text", default="",
                  help="e.g. ABT; blank = team with most issues"),
        ],
    ),
    "logfire": Source(
        id="logfire", label="Logfire", env_key="LOGFIRE_READ_TOKEN", kind="logfire-json",
        view_app="logfire", can_slice=False, artifact="logfire.json",
        capture=_capture_logfire, slice=None,
        params=[
            Param("until", "Cutoff (until = T)", "datetime", default=DEFAULT_T, required=True,
                  help="captured as-of this timestamp"),
            Param("incident_hours", "Incident window (h)", "text", default="2"),
            Param("period_days", "Overview look-back (d)", "text", default="365"),
        ],
    ),
}


def source_summaries() -> List[Dict[str, Any]]:
    """UI-facing source list — credential PRESENCE only, never the value."""
    out = []
    for s in SOURCES.values():
        out.append({
            "id": s.id, "label": s.label, "kind": s.kind, "view_app": s.view_app,
            "env_key": s.env_key, "has_key": s.has_key(), "can_slice": s.can_slice,
            "params": [p.__dict__ for p in s.params],
        })
    return out

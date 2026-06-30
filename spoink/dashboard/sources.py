"""Source registry — the single place that knows how to CAPTURE, SLICE, and (for nice UIs)
DISCOVER selectable options for each upstream, wrapping spoink's existing export/slice modules.

Each Source declares:
  * env_key   — the .env var holding its credential (presence is surfaced to the UI; the
                value is NEVER returned over the API).
  * params    — the capture-form schema (so the frontend renders the right inputs, incl.
                `datetime` pickers and `discover`-backed multi-selects).
  * capture() — runs the real spoink fetch+write into a run dir, returns a small report.
  * slice()   — time-aligns a captured artifact to the incident cutoff T (where supported);
                Logfire/GitHub are captured/aligned as-of-T directly, so they don't slice.
  * options() — lists selectable values for a discoverable param (channels, teams, …) so the
                user picks from checkboxes instead of typing names.
  * view_app  — the seed-dashboard app id used to display the produced overlay.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
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
    kind: str = "text"          # text | datetime | number | select | multiselect
    default: str = ""
    required: bool = False
    help: str = ""
    discover: str = ""          # if set, the param's options come from Source.options(discover)


@dataclass
class Source:
    id: str
    label: str
    env_key: str
    kind: str                   # artifact kind
    view_app: Optional[str]
    params: List[Param]
    can_slice: bool
    capture: Callable[[str, Dict[str, Any]], Dict[str, Any]]
    slice: Optional[Callable[[str, str, float], Dict[str, Any]]] = None
    options: Optional[Callable[[str], Dict[str, Any]]] = None
    artifact: str = ""
    note: str = ""              # honest one-liner shown in the UI (e.g. realism caveat)

    def has_key(self) -> bool:
        return bool(os.environ.get(self.env_key)) if self.env_key else True


def _resolve_t(v: Any) -> str:
    """Resolve a 'snapshot as of' value to an ISO-Z timestamp. Empty / 'now' -> current UTC."""
    from datetime import datetime, timezone
    s = str(v or "").strip().lower()
    if not s or s == "now":
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return str(v).strip()


# =========================================================================== Slack
def _capture_slack(run_dir: str, params: Dict[str, Any]) -> Dict[str, Any]:
    from .. import slack_export as sx
    from ..slice import parse_cutoff
    token = _require_env("SLACK_USER_TOKEN")
    channels = _as_list(params.get("channels"))
    if not channels:
        raise CaptureError("slack: pick at least one channel")
    since = params.get("since") or "2y"
    oldest = sx.parse_oldest(since)
    as_of = _resolve_t(params.get("as_of"))
    latest = f"{parse_cutoff(as_of, None):.6f}"
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
    return {"artifact": "slack-export", "as_of": as_of, "channels": channels, "since": since,
            "counts": counts, "sufficient": rep.get("sufficient_for_task_gen"), "report": rep}


def _slice_slack(run_dir: str, artifact: str, cutoff: float) -> Dict[str, Any]:
    from ..slice import slice_export
    res = slice_export(str(Path(run_dir) / artifact), str(Path(run_dir) / "slack-export@T"), cutoff)
    return {"artifact": "slack-export@T", "kept": res["kept"], "dropped": res["dropped"],
            "last_kept": res.get("last_kept"), "report": res}


def _options_slack(param: str, **_) -> Dict[str, Any]:
    from .. import slack_export as sx
    if param != "channels":
        return {"kind": "multiselect", "options": []}
    token = _require_env("SLACK_USER_TOKEN")
    client = sx.SlackClient(token)
    out = []
    try:
        for ch in client.paginate("conversations.list", "channels",
                                  types="public_channel,private_channel", limit=200):
            out.append({"value": ch.get("name"), "label": ch.get("name"),
                        "member": bool(ch.get("is_member")), "private": bool(ch.get("is_private")),
                        "count": ch.get("num_members")})
            if len(out) >= 1000:
                break
    finally:
        client.close()
    # members first (the rich channels you're actually in), then by name
    out.sort(key=lambda c: (not c["member"], (c["label"] or "").lower()))
    return {"kind": "multiselect", "options": out}


# =========================================================================== Linear
def _capture_linear(run_dir: str, params: Dict[str, Any]) -> Dict[str, Any]:
    from .. import linear_export as lx
    from ..slice import parse_cutoff, slice_tracker
    key = _require_env("LINEAR_API_KEY")
    as_of = _resolve_t(params.get("as_of"))
    client = lx.LinearClient(key)
    try:
        data = lx.fetch_workspace(client, params.get("team") or None)
        probe = lx.run_probe(client)
        state = lx.to_state(data)
        rep = lx.build_report(probe, state, data)
    finally:
        client.close()
    # snapshot as-of: creation-cut the tracker to the chosen moment (issues/comments <= as_of)
    sl = slice_tracker(state, parse_cutoff(as_of, None))
    (Path(run_dir) / "state.json").write_text(json.dumps(state, indent=2, ensure_ascii=False))
    return {"artifact": "state.json", "as_of": as_of, "team": rep.get("team"),
            "issues_kept": sl.get("issues_kept"), "issues_dropped": sl.get("issues_dropped"),
            "comments_kept": sl.get("comments_kept"),
            "sufficient": rep.get("sufficient_for_task_gen"), "report": rep}


def _slice_linear(run_dir: str, artifact: str, cutoff: float) -> Dict[str, Any]:
    from ..slice import slice_tracker
    state = json.loads((Path(run_dir) / artifact).read_text())
    res = slice_tracker(state, cutoff)
    (Path(run_dir) / "state@T.json").write_text(json.dumps(state, indent=2, ensure_ascii=False))
    return {"artifact": "state@T.json", **res}


def _options_linear(param: str, **_) -> Dict[str, Any]:
    from .. import linear_export as lx
    if param != "team":
        return {"kind": "select", "options": []}
    key = _require_env("LINEAR_API_KEY")
    client = lx.LinearClient(key)
    out = []
    try:
        for t in client.paginate(lx.Q_TEAMS, "teams"):
            out.append({"value": t.get("key"), "label": f"{t.get('key')} · {t.get('name')}",
                        "count": t.get("issueCount")})
    finally:
        client.close()
    out.sort(key=lambda t: -(t.get("count") or 0))
    return {"kind": "select", "options": out}


# =========================================================================== Logfire
def _capture_logfire(run_dir: str, params: Dict[str, Any]) -> Dict[str, Any]:
    from datetime import datetime, timedelta, timezone
    from .. import logfire_export as gx
    token = _require_env("LOGFIRE_READ_TOKEN")
    as_of = _resolve_t(params.get("as_of"))
    incident_hours = float(params.get("incident_hours") or 2.0)
    period_days = float(params.get("period_days") or 365.0)
    cutoff = datetime.fromisoformat(as_of.replace("Z", "+00:00")).astimezone(timezone.utc)
    fz = lambda d: d.strftime("%Y-%m-%dT%H:%M:%SZ")
    client = gx.LogfireClient(token)
    try:
        data = gx.fetch(client, fz(cutoff - timedelta(hours=incident_hours)), fz(cutoff),
                        fz(cutoff - timedelta(days=period_days)))
        rep = gx.build_report(data)
    finally:
        client.close()
    (Path(run_dir) / "logfire.json").write_text(json.dumps(data, indent=2))
    (Path(run_dir) / "records.json").write_text(json.dumps(data.get("incident", []), indent=2))  # gateway bake input
    (Path(run_dir) / "gauge-state.json").write_text(json.dumps(gx.to_gauge_state(data), indent=2))
    return {"artifact": "logfire.json", "gauge_artifact": "gauge-state.json", "as_of": as_of,
            "incident_records": rep.get("incident_records"),
            "overview_signatures": rep.get("overview_signatures"),
            "sufficient": rep.get("sufficient"), "report": rep}


# =========================================================================== GitHub (ghc snapshot)
def _gh_token() -> str:
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not tok:
        raise CaptureError("github: set GITHUB_TOKEN (or GH_TOKEN) in .env")
    return tok


def _list_org_repos(org: str, token: str) -> List[Dict[str, Any]]:
    """All repos under an org (or user) via the GitHub REST API, paginated."""
    import httpx
    out: List[Dict[str, Any]] = []
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    with httpx.Client(timeout=30, headers=headers) as c:
        for base in (f"https://api.github.com/orgs/{org}/repos",
                     f"https://api.github.com/users/{org}/repos"):
            page = 1
            ok = False
            while True:
                r = c.get(base, params={"per_page": 100, "page": page, "type": "all", "sort": "pushed"})
                if r.status_code == 404:
                    break              # not an org -> try the users endpoint
                r.raise_for_status()
                ok = True
                batch = r.json()
                if not batch:
                    break
                out.extend(batch)
                page += 1
            if ok:
                break
    return out


def _options_github(param: str, **kw) -> Dict[str, Any]:
    if param != "repos":
        return {"kind": "multiselect", "options": []}
    org = (kw.get("org") or "").strip()
    if not org:
        return {"kind": "multiselect", "options": [], "note": "enter an org/owner to list repos"}
    repos = _list_org_repos(org, _gh_token())
    opts = [{"value": r["name"], "label": r["name"],
             "private": bool(r.get("private")), "archived": bool(r.get("archived"))} for r in repos]
    opts.sort(key=lambda o: (o["archived"], o["label"].lower()))
    return {"kind": "multiselect", "options": opts}


def _capture_github(run_dir: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Freeze one OR MANY GitHub repos to a snapshot artifact via `ghc-hydrate snapshot` — i.e.
    a whole org's GitHub state. T-alignment is deferred to bake time (`apply --as-of T` per repo
    into one Forgejo), so there's no separate slice. Needs `ghc-hydrate` on PATH (or
    $GHC_HYDRATE_BIN) + GITHUB_TOKEN. Empty repo selection = ALL repos in the org."""
    org = (params.get("org") or "").strip()
    repos = _as_list(params.get("repos"))
    as_of = _resolve_t(params.get("as_of"))
    if not org and not repos:
        raise CaptureError("github: set an org/owner (and optionally pick repos)")
    ghc = os.environ.get("GHC_HYDRATE_BIN") or shutil.which("ghc-hydrate")
    if not ghc:
        raise CaptureError("github: ghc-hydrate not found (set $GHC_HYDRATE_BIN or install gh-cli-clone)")
    token = _gh_token()
    if not repos:                                   # empty selection -> snapshot the whole org
        repos = [r["name"] for r in _list_org_repos(org, token)]
        if not repos:
            raise CaptureError(f"github: no repos found for {org!r}")
    snaps = Path(run_dir) / "snapshots"
    snaps.mkdir(parents=True, exist_ok=True)
    done, failed = [], []
    for r in repos:
        full = r if "/" in r else f"{org}/{r}"
        out = snaps / full.replace("/", "__")
        p = subprocess.run([ghc, "snapshot", full, "--out", str(out), "--token", token],
                           capture_output=True, text=True, timeout=3600)
        (done if p.returncode == 0 else failed).append(
            full if p.returncode == 0 else {"repo": full, "err": (p.stderr or p.stdout)[-200:]})
    manifest = {"org": org, "repos": done, "failed": failed, "count": len(done), "as_of": as_of}
    (snaps / "manifest.json").write_text(json.dumps(manifest, indent=2))
    if not done:
        raise CaptureError(f"github: all {len(repos)} snapshots failed; first: {failed[:1]}")
    return {"artifact": "snapshots", "org": org, "as_of": as_of, "repos": len(done),
            "repo_names": done, "failed": len(failed),
            "note": "apply each --as-of T into one Forgejo at bake"}


# =========================================================================== helpers + registry
def _as_list(v: Any) -> List[str]:
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    return [s.strip() for s in str(v or "").split(",") if s.strip()]


_AS_OF = Param("as_of", "Snapshot as of", "datetime", default="now",
               help="the moment to snapshot — defaults to now")

SOURCES: Dict[str, Source] = {
    "slack": Source(
        id="slack", label="Slack", env_key="SLACK_USER_TOKEN", kind="slack-export",
        view_app="slack", can_slice=True, artifact="slack-export",
        capture=_capture_slack, slice=_slice_slack, options=_options_slack,
        params=[
            Param("channels", "Channels", "multiselect", required=True, discover="channels",
                  help="pick the channels to capture (you're a member of the rich private ones)"),
            Param("since", "History", "text", default="2y", help="how far back: 90d | 12h | all | YYYY-MM-DD"),
            _AS_OF,
        ],
    ),
    "linear": Source(
        id="linear", label="Linear", env_key="LINEAR_API_KEY", kind="jira-state",
        view_app="jira", can_slice=True, artifact="state.json",
        capture=_capture_linear, slice=_slice_linear, options=_options_linear,
        params=[
            Param("team", "Team", "select", discover="team", help="blank = team with the most issues"),
            _AS_OF,
        ],
    ),
    "logfire": Source(
        id="logfire", label="Logfire", env_key="LOGFIRE_READ_TOKEN", kind="logfire-json",
        view_app="logfire", can_slice=False, artifact="logfire.json",
        capture=_capture_logfire, slice=None,
        params=[
            _AS_OF,
            Param("incident_hours", "Incident window (hours)", "number", default="2"),
            Param("period_days", "Overview look-back (days)", "number", default="365"),
        ],
    ),
    "github": Source(
        id="github", label="GitHub", env_key="GITHUB_TOKEN", kind="ghc-snapshot",
        view_app="github", can_slice=False, artifact="snapshots",
        capture=_capture_github, slice=None, options=_options_github,
        note="snapshot one or many repos (a whole org); time-aligned at bake (needs ghc-hydrate + GITHUB_TOKEN)",
        params=[
            Param("org", "Org / owner", "text", required=True, help="e.g. abundant-ai"),
            Param("repos", "Repos", "multiselect", discover="repos",
                  help="pick repos to freeze; leave empty = ALL repos in the org"),
            _AS_OF,
        ],
    ),
}

# which sources can be baked + pushed to GHCR (github bakes via a boot->hydrate->commit
# of a ghc-service Forgejo image rather than a single `docker build`; see gateway/build_forge.sh)
PUBLISHABLE = {"slack", "linear", "logfire", "github"}


def source_summaries() -> List[Dict[str, Any]]:
    """UI-facing source list — credential PRESENCE only, never the value."""
    return [{
        "id": s.id, "label": s.label, "kind": s.kind, "view_app": s.view_app,
        "env_key": s.env_key, "has_key": s.has_key(), "can_slice": s.can_slice,
        "publishable": s.id in PUBLISHABLE,
        "note": s.note, "params": [p.__dict__ for p in s.params],
    } for s in SOURCES.values()]

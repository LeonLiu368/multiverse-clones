"""Incident discovery -> candidate queue.

The Task Creator's hard part: scan points in time for *unresolved incidents* worth snapshotting.
An "incident" is inferred, not stored anywhere in the surfaces. A candidate is a moment T where
something was broken and a later action fixed it — that later action is both the anti-leakage cut
(snapshot as_of < resolution) and the machine-checkable oracle.

Feeds are pluggable (register via @feed). The slice wires `github_revert` deeply — a live,
lightweight PR scan (no full snapshot needed to discover). Logfire/Slack/Linear/CI feeds slot into
the same Candidate shape later.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional

import httpx

GITHUB_API = "https://api.github.com"

# a PR whose title/branch matches these is (very likely) resolving a prod incident
_REVERT = re.compile(r"\brevert(s|ed|ing)?\b", re.I)
_HOTFIX = re.compile(r"\b(hotfix|rollback|roll back|revert|emergency|incident|sev-?\d|outage|regress)", re.I)
_FIX = re.compile(r"^\s*(fix|bug|patch)\b", re.I)


@dataclass
class Candidate:
    """One discovered incident, ready to be snapshotted + turned into a task."""
    id: str                              # stable (feed + repo + pr)
    feed: str                            # "github_revert" | ...
    t: str                               # incident moment (ISO-Z) = the snapshot anchor (unresolved AT t)
    title: str                           # incident message/descriptor
    summary: str                         # human one-liner of what happened + how it was resolved
    required_data: Dict[str, Any]        # per-surface: what the task needs (source -> params)
    resolution: Dict[str, Any]           # the oracle: {repo, pr, base_sha, head_sha, merged_at, ...}
    score: float = 0.0                   # ranking (higher = better task material)
    signals: List[str] = field(default_factory=list)   # why it scored (has_tests, revert, small_diff, ...)
    status: str = "new"                  # new | attached | captured | generated
    snapshots: Dict[str, str] = field(default_factory=dict)   # source -> attached run_id

    def surfaces(self) -> List[str]:
        return list(self.required_data.keys())


FEEDS: Dict[str, Callable[..., List[Candidate]]] = {}


def feed(name: str):
    def deco(fn):
        FEEDS[name] = fn
        return fn
    return deco


def _cid(feed: str, *parts: Any) -> str:
    return f"{feed}-" + hashlib.sha1("/".join(str(p) for p in parts).encode()).hexdigest()[:10]


def _client(token: str) -> httpx.Client:
    return httpx.Client(timeout=30, headers={
        "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"})


def _org_repos(c: httpx.Client, org: str, limit: int) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for base in (f"{GITHUB_API}/orgs/{org}/repos", f"{GITHUB_API}/users/{org}/repos"):
        page, ok = 1, False
        while len(out) < limit:
            r = c.get(base, params={"per_page": 100, "page": page, "sort": "pushed", "type": "all"})
            if r.status_code == 404:
                break
            r.raise_for_status(); ok = True
            batch = r.json()
            if not batch:
                break
            out.extend(batch); page += 1
        if ok:
            break
    return out[:limit]


def _pr_touches_tests(c: httpx.Client, owner: str, repo: str, num: int) -> bool:
    """Does the PR change a test file? (proxy for 'F2P is derivable')."""
    try:
        files = c.get(f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{num}/files",
                      params={"per_page": 100}).json()
    except Exception:
        return False
    return any(re.search(r"(^|/)tests?/|_test\.|test_.*\.py|\.test\.", f.get("filename", "")) for f in files)


@feed("github_revert")
def github_revert(token: str, org: str, window_days: int = 120, per_repo: int = 60,
                  max_repos: int = 40, max_candidates: int = 60, **_) -> List[Candidate]:
    """Live scan: merged PRs across an org that look like incident resolutions (revert/hotfix/fix).
    Each becomes a candidate anchored at the PR's open time (incident in flight, fix not yet landed)."""
    from datetime import datetime, timedelta, timezone
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    cands: List[Candidate] = []
    with _client(token) as c:
        for repo in _org_repos(c, org, max_repos):
            owner, name = repo["full_name"].split("/", 1)
            if repo.get("archived"):
                continue
            prs = c.get(f"{GITHUB_API}/repos/{owner}/{name}/pulls",
                        params={"state": "closed", "sort": "updated", "direction": "desc",
                                "per_page": per_repo})
            if prs.status_code != 200:
                continue
            for pr in prs.json():
                merged = pr.get("merged_at")
                if not merged:
                    continue
                if datetime.fromisoformat(merged.replace("Z", "+00:00")) < cutoff:
                    continue
                title = pr.get("title") or ""
                branch = (pr.get("head") or {}).get("ref") or ""
                body = pr.get("body") or ""
                # revert must be in the TITLE or BRANCH — body mentions are noise (changelogs list reverts)
                is_revert = bool(_REVERT.search(title) or _REVERT.search(branch))
                is_hotfix = bool(_HOTFIX.search(title) or _HOTFIX.search(branch))
                is_fix = bool(_FIX.search(title))
                if not (is_revert or is_hotfix or is_fix):
                    continue
                num = pr["number"]
                signals: List[str] = []
                score = 0.0
                if is_revert: signals.append("revert"); score += 3
                if is_hotfix: signals.append("hotfix"); score += 2
                if is_fix:    signals.append("fix");    score += 1
                if re.search(r"#\d+", body):            signals.append("links_issue"); score += 1
                has_tests = _pr_touches_tests(c, owner, name, num)
                if has_tests: signals.append("has_tests"); score += 2   # F2P derivable
                # anchor just BEFORE the fix landed (incident live, fix not yet merged) — not
                # PR-open time, which can be months earlier for a long-lived branch
                mdt = datetime.fromisoformat(merged.replace("Z", "+00:00")) - timedelta(minutes=1)
                t = mdt.strftime("%Y-%m-%dT%H:%M:%SZ")
                cands.append(Candidate(
                    id=_cid("github_revert", repo["full_name"], num),
                    feed="github_revert", t=t,
                    title=f"{title.strip()}  ({repo['full_name']}#{num})",
                    summary=(f"{repo['full_name']}#{num} '{title.strip()}' — "
                             f"signals={','.join(signals) or 'fix'}. The snapshot is the SUT just before "
                             f"this fix landed."),
                    required_data={
                        "github": {"org": owner, "repos": [name], "as_of": t},   # SUT @ incident tip (REQUIRED)
                        "logfire": {"as_of": t, "incident_hours": 2, "period_days": 30},  # symptom (optional)
                        "slack":   {"as_of": t},                                  # chatter (optional)
                        "linear":  {"as_of": t},                                  # tickets (optional)
                    },
                    resolution={"repo": repo["full_name"], "pr": num,
                                "base_sha": (pr.get("base") or {}).get("sha", ""),
                                "head_sha": pr.get("merge_commit_sha") or (pr.get("head") or {}).get("sha", ""),
                                "merged_at": merged, "has_tests": has_tests},
                    score=score, signals=signals))
                if len(cands) >= max_candidates:
                    break
            if len(cands) >= max_candidates:
                break
    cands.sort(key=lambda x: -x.score)
    return cands


@feed("github_ci")
def github_ci(token: str, org: str, window_days: int = 120, per_repo: int = 80,
              max_repos: int = 30, max_candidates: int = 60, **_) -> List[Candidate]:
    """Live scan: a CI run that went red on the default branch then green again. The failing
    commit is the incident tip; the commit that turned it green is the fix (base->head oracle).
    This is the 'bad deploy / CI failure' feed."""
    from datetime import datetime, timedelta, timezone
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    cands: List[Candidate] = []
    with _client(token) as c:
        for repo in _org_repos(c, org, max_repos):
            owner, name = repo["full_name"].split("/", 1)
            if repo.get("archived"):
                continue
            branch = repo.get("default_branch") or "main"
            r = c.get(f"{GITHUB_API}/repos/{owner}/{name}/actions/runs",
                      params={"branch": branch, "event": "push", "status": "completed", "per_page": per_repo})
            if r.status_code != 200:
                continue
            runs = [w for w in r.json().get("workflow_runs", [])
                    if w.get("conclusion") in ("success", "failure")]
            # per workflow, walk oldest->newest looking for failure then a later success
            by_wf: Dict[Any, List[Dict[str, Any]]] = {}
            for w in runs:
                by_wf.setdefault(w.get("workflow_id"), []).append(w)
            for wf, ws in by_wf.items():
                ws.sort(key=lambda w: w.get("created_at") or "")
                for i, w in enumerate(ws):
                    if w.get("conclusion") != "failure":
                        continue
                    created = w.get("created_at") or ""
                    if not created or datetime.fromisoformat(created.replace("Z", "+00:00")) < cutoff:
                        continue
                    nxt = next((n for n in ws[i + 1:] if n.get("conclusion") == "success"), None)
                    if not nxt:
                        continue
                    base = w.get("head_sha", ""); head = nxt.get("head_sha", "")
                    if not base or not head or base == head:
                        continue
                    wfname = w.get("name") or "CI"
                    msg = ((w.get("head_commit") or {}).get("message") or "").splitlines()[0][:60]
                    cands.append(Candidate(
                        id=_cid("github_ci", repo["full_name"], base[:12]),
                        feed="github_ci", t=created,
                        title=f"{wfname} red on {name}@{base[:8]}: {msg}",
                        summary=(f"{repo['full_name']} '{wfname}' failed at {base[:8]}, went green at "
                                 f"{head[:8]}. The snapshot at T is the broken tree, before the fix."),
                        required_data={
                            "github": {"org": owner, "repos": [name], "as_of": created},
                            "logfire": {"as_of": created, "incident_hours": 2, "period_days": 30},
                            "slack": {"as_of": created}, "linear": {"as_of": created}},
                        resolution={"repo": repo["full_name"], "pr": None, "base_sha": base,
                                    "head_sha": head, "merged_at": nxt.get("created_at"),
                                    "workflow": wfname, "has_tests": True},
                        score=2.0, signals=["ci_failure"]))
                    break   # one candidate per workflow is plenty
            if len(cands) >= max_candidates:
                break
    return cands[:max_candidates]


@feed("logfire_anomaly")
def logfire_anomaly(token: str, window_days: int = 14, max_candidates: int = 40, **_) -> List[Candidate]:
    """Live scan of Logfire: distinct error/exception signatures in the window become DIAGNOSIS
    candidates anchored at each signature's first-seen. No code oracle — ground truth is the
    signature + service (a readback/diagnosis task)."""
    from datetime import datetime, timedelta, timezone
    from .. import logfire_export as gx
    now = datetime.now(timezone.utc)
    fz = lambda d: d.strftime("%Y-%m-%dT%H:%M:%SZ")
    client = gx.LogfireClient(token)
    try:
        # discovery only needs the SIGNATURE overview — skip the heavy paged incident pull
        overview = client.query(gx.OVERVIEW_SQL, fz(now - timedelta(days=window_days)), fz(now), limit=2000)
    finally:
        client.close()
    cands: List[Candidate] = []
    for sig in (overview or []):
        if not sig.get("exception_type"):
            continue
        first = (sig.get("first_seen") or "")[:19]
        t = (first + "Z") if first and not first.endswith("Z") else (first or fz(now))
        svc = sig.get("service_name") or "?"
        cands.append(Candidate(
            id=_cid("logfire_anomaly", svc, sig.get("exception_type"), sig.get("message", "")[:40]),
            feed="logfire_anomaly", t=t,
            title=f"{sig['exception_type']} in {svc} (x{sig.get('n', '?')})",
            summary=(f"{svc}: {sig['exception_type']} — {(sig.get('exception_message') or '')[:80]}. "
                     f"{sig.get('n', '?')} occurrences; first seen at T. Diagnose the root cause."),
            required_data={"logfire": {"as_of": t, "incident_hours": 3, "period_days": 30},
                           "slack": {"as_of": t}},
            resolution={"service": svc, "exception_type": sig.get("exception_type"),
                        "signature": sig.get("message", ""), "count": sig.get("n"), "kind": "diagnosis"},
            score=min(5.0, 1.0 + (sig.get("n") or 0) / 50.0), signals=["exception", svc]))
        if len(cands) >= max_candidates:
            break
    cands.sort(key=lambda x: -x.score)
    return cands


# single words only — Slack search returns nothing for quoted phrases mixed with OR
_SLACK_INCIDENT_Q = ("incident OR outage OR SEV OR sev1 OR pager OR paged OR hotfix OR "
                     "rollback OR regression OR downtime OR degraded OR firefighting")


@feed("slack_incident")
def slack_incident(token: str, window_days: int = 30, max_candidates: int = 40, **_) -> List[Candidate]:
    """Live scan of Slack: messages that read like an incident being called become DIAGNOSIS
    candidates anchored at the message time. Ground truth = the incident + how it was resolved
    (from the thread); no code oracle. Needs search.messages (user token)."""
    from datetime import datetime, timedelta, timezone
    from ..slack_export import SlackClient, SlackError
    after = (datetime.now(timezone.utc) - timedelta(days=window_days)).strftime("%Y-%m-%d")
    client = SlackClient(token)
    try:
        # NB: sort="timestamp" mysteriously zeroes results for OR queries — default (relevance) works
        resp = client.ok_call("search.messages", query=f"{_SLACK_INCIDENT_Q} after:{after}", count=100)
    except SlackError:
        client.close(); return []                       # search denied -> feed unavailable
    client.close()
    matches = ((resp.get("messages") or {}).get("matches")) or []
    cands: List[Candidate] = []
    seen: set = set()
    for m in matches:
        ch = m.get("channel") or {}
        chan = ch.get("name") or ch.get("id") or "?"
        ts = m.get("ts") or ""
        text = (m.get("text") or "").replace("\n", " ").strip()
        key = (chan, text[:50])
        if not ts or key in seen:
            continue
        seen.add(key)
        try:
            t = datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            continue
        cands.append(Candidate(
            id=_cid("slack_incident", chan, ts),
            feed="slack_incident", t=t,
            title=f"#{chan}: {text[:60]}",
            summary=(f"Slack #{chan}: '{text[:120]}'. Diagnose the incident being discussed and "
                     f"identify the root cause / resolution."),
            required_data={"slack": {"channels": [chan], "as_of": t},
                           "logfire": {"as_of": t, "incident_hours": 3, "period_days": 30},
                           "github": {"as_of": t}, "linear": {"as_of": t}},
            resolution={"channel": chan, "ts": ts, "kind": "diagnosis"},
            score=2.0, signals=["slack", chan]))
        if len(cands) >= max_candidates:
            break
    return cands


Q_LINEAR_SEV = (
    "query($after:String){ issues(first:50, after:$after, filter:{ completedAt:{ null:false }, "
    "or:[ {priority:{eq:1}}, {labels:{some:{name:{containsIgnoreCase:\"incident\"}}}}, "
    "{labels:{some:{name:{containsIgnoreCase:\"sev\"}}}}, {labels:{some:{name:{containsIgnoreCase:\"outage\"}}}}, "
    "{labels:{some:{name:{containsIgnoreCase:\"regression\"}}}} ] }){ "
    "pageInfo{ hasNextPage endCursor } nodes { identifier title description priority createdAt "
    "completedAt state{ name type } labels{ nodes{ name } } team{ key } } } }")


@feed("linear_sev")
def linear_sev(token: str, window_days: int = 120, max_candidates: int = 40, **_) -> List[Candidate]:
    """Live scan of Linear: completed SEV/incident/urgent issues become DIAGNOSIS candidates
    anchored at the report time (createdAt). Ground truth = the issue's resolution."""
    from datetime import datetime, timedelta, timezone
    from ..linear_export import LinearClient, LinearError
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    client = LinearClient(token)
    cands: List[Candidate] = []
    try:
        seen_pages = 0
        for it in client.paginate(Q_LINEAR_SEV, "issues"):
            seen_pages += 1
            if seen_pages > 500:
                break
            ca = it.get("createdAt") or ""
            if not ca:
                continue
            try:
                if datetime.fromisoformat(ca.replace("Z", "+00:00")) < cutoff:
                    continue
            except Exception:
                continue
            ident = it.get("identifier") or "?"
            title = (it.get("title") or "").strip()
            labels = [l.get("name") for l in (it.get("labels") or {}).get("nodes", [])]
            t = ca[:19] + "Z" if not ca.endswith("Z") else ca
            cands.append(Candidate(
                id=_cid("linear_sev", ident),
                feed="linear_sev", t=t,
                title=f"{ident}: {title[:60]}",
                summary=(f"Linear {ident} '{title}' (labels: {', '.join(labels) or 'urgent'}). "
                         f"Diagnose the reported incident and its resolution."),
                required_data={"linear": {"as_of": t}, "slack": {"as_of": t},
                               "logfire": {"as_of": t, "incident_hours": 3, "period_days": 30},
                               "github": {"as_of": t}},
                resolution={"issue": ident, "team": (it.get("team") or {}).get("key"),
                            "labels": labels, "completed_at": it.get("completedAt"), "kind": "diagnosis"},
                score=3.0 if labels else 1.5,          # labelled incidents rank above urgent-only
                signals=["linear"] + (labels[:2] or ["urgent"])))
            if len(cands) >= max_candidates:
                break
    except LinearError:
        return []
    finally:
        client.close()
    return cands


# which env credential each feed needs (the server resolves + passes it as `token`)
FEED_ENV = {"github_revert": "GITHUB_TOKEN", "github_ci": "GITHUB_TOKEN",
            "logfire_anomaly": "LOGFIRE_READ_TOKEN",
            "slack_incident": "SLACK_USER_TOKEN", "linear_sev": "LINEAR_API_KEY"}

# feed taxonomy (single source of truth for the UI). Every feed mines one SOURCE for one SIGNAL
# and yields one task SHAPE:
#   fix      — a code-fix task with an empirical nop/oracle proof (provable end-to-end, no surfaces).
#   diagnose — a symptom-driven task graded by a HIDDEN test; needs evidence surfaces attached at T.
# The old flat dropdown mixed source and signal on one axis; this makes both explicit so the picker
# groups by source and shows what you actually get.
FEED_META = {
    "github_revert":   {"source": "github",  "signal": "Revert / hotfix PR",     "shape": "fix",      "provable": True},
    "github_ci":       {"source": "github",  "signal": "CI failure → green",     "shape": "fix",      "provable": True},
    "logfire_anomaly": {"source": "logfire", "signal": "Error / anomaly spike",  "shape": "diagnose", "provable": False},
    "slack_incident":  {"source": "slack",   "signal": "Incident thread",        "shape": "diagnose", "provable": False},
    "linear_sev":      {"source": "linear",  "signal": "SEV / incident ticket",  "shape": "diagnose", "provable": False},
}
SOURCE_LABEL = {"github": "GitHub", "logfire": "Logfire", "slack": "Slack", "linear": "Linear"}


def discover(feed_name: str, token: str, **kw) -> List[Candidate]:
    fn = FEEDS.get(feed_name)
    if not fn:
        raise ValueError(f"unknown feed {feed_name!r}; have {sorted(FEEDS)}")
    return fn(token=token, **kw)


def to_dict(c: Candidate) -> Dict[str, Any]:
    return asdict(c)


class CandidateQueue:
    """Persisted candidate queue (newest-discovered first, deduped by candidate id)."""
    def __init__(self, path):
        from pathlib import Path
        self.path = Path(path)
        self.items: Dict[str, Dict[str, Any]] = self._load()

    def _load(self) -> Dict[str, Dict[str, Any]]:
        import json
        try:
            return {c["id"]: c for c in json.loads(self.path.read_text())}
        except Exception:
            return {}

    def _save(self) -> None:
        import json
        ordered = sorted(self.items.values(), key=lambda c: (-c.get("score", 0), c.get("t", "")))
        self.path.write_text(json.dumps(ordered, indent=2))

    def merge(self, cands: List[Candidate]) -> int:
        """Add new candidates and REFRESH existing ones with the latest discovered fields (t,
        summary, resolution, score, …) — so anchor/heuristic fixes reach already-queued items —
        while preserving triage state (status + attached snapshots)."""
        added = 0
        for c in cands:
            d = to_dict(c)
            old = self.items.get(c.id)
            if old:
                d["snapshots"] = old.get("snapshots") or {}
                d["status"] = old.get("status", "new")   # keep where it is in the pipeline
            else:
                added += 1
            self.items[c.id] = d
        self._save()
        return added

    def list(self) -> List[Dict[str, Any]]:
        return sorted(self.items.values(), key=lambda c: (-c.get("score", 0), c.get("t", "")))

    def get(self, cid: str) -> Optional[Dict[str, Any]]:
        return self.items.get(cid)

    def update(self, cid: str, **fields) -> Optional[Dict[str, Any]]:
        c = self.items.get(cid)
        if not c:
            return None
        c.update(fields); self._save()
        return c

    def remove(self, cid: str) -> bool:
        ok = self.items.pop(cid, None) is not None
        if ok:
            self._save()
        return ok

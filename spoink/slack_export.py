"""Slack workspace export via the Web API (read-only, xoxp user token).

First module of `spoink`, the snapshot engine. Pulls a few channels over a recent
window into the **standard Slack export directory layout** so that
`abundant-slack-clone`'s existing `import_export()` can ingest it with no new
conversion code. The real deliverable is the sufficiency report: which API
methods/scopes the token actually has, and whether that's enough for task-gen.

Read-only by design. Token comes only from the env var SLACK_USER_TOKEN; it is
never logged, echoed, or written to disk. Write-back is intentionally not here.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional

import httpx

SLACK_API = "https://slack.com/api/"

# Methods we exercise, with the scope that typically gates each (for the report).
PROBE_METHODS = [
    ("auth.test", None),
    ("users.list", "users:read"),
    ("conversations.list", "channels:read"),
    ("conversations.history", "channels:history"),
    ("conversations.replies", "channels:history"),
    ("conversations.members", "channels:read"),
    ("search.messages", "search:read (user token only)"),
]


class SlackError(Exception):
    def __init__(self, method: str, error: str, payload: Dict[str, Any]):
        super().__init__(f"{method}: {error}")
        self.method = method
        self.error = error
        self.payload = payload


# --------------------------------------------------------------------------- client


class SlackClient:
    """Thin Slack Web API wrapper: bearer auth, ok-envelope, cursor pagination,
    429 backoff. Read-only methods only."""

    def __init__(self, token: str, *, timeout: float = 30.0):
        self._http = httpx.Client(
            base_url=SLACK_API,
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
        )
        self.rate_limit_stalls = 0

    def close(self) -> None:
        self._http.close()

    def call(self, method: str, **params: Any) -> Dict[str, Any]:
        data = {k: v for k, v in params.items() if v is not None}
        for _ in range(8):
            r = self._http.post(method, data=data)
            if r.status_code == 429:
                self.rate_limit_stalls += 1
                time.sleep(int(r.headers.get("Retry-After", "2")))
                continue
            r.raise_for_status()
            return r.json()
        raise RuntimeError(f"{method}: rate-limited repeatedly")

    def ok_call(self, method: str, **params: Any) -> Dict[str, Any]:
        j = self.call(method, **params)
        if not j.get("ok"):
            raise SlackError(method, j.get("error", "unknown"), j)
        return j

    def paginate(self, method: str, key: str, **params: Any) -> Iterator[Dict[str, Any]]:
        cursor: Optional[str] = None
        while True:
            j = self.ok_call(method, cursor=cursor, **params)
            for item in j.get(key, []) or []:
                yield item
            cursor = (j.get("response_metadata") or {}).get("next_cursor") or None
            if not cursor:
                break


# --------------------------------------------------------------------------- fetch


def _norm_name(name: str) -> str:
    return name.lstrip("#").strip().lower()


def fetch_workspace(
    client: Any, target_channels: List[str], oldest: str
) -> Dict[str, Any]:
    """Pull users, the requested channels, and their messages+threads since `oldest`.

    `client` only needs `ok_call` and `paginate` (so tests can inject a fake).
    Returns raw Slack objects (unmodified) bucketed for the export writer.
    """
    auth = client.ok_call("auth.test")
    workspace = {
        "id": auth.get("team_id", "T0"),
        "name": auth.get("team", "workspace"),
        "domain": (auth.get("url", "") or "").replace("https://", "").split(".")[0] or "workspace",
    }

    users = list(client.paginate("users.list", "members", limit=200))

    wanted = {_norm_name(c) for c in target_channels}
    all_channels = list(
        client.paginate(
            "conversations.list", "channels",
            types="public_channel,private_channel", exclude_archived="false", limit=200,
        )
    )
    channels = [c for c in all_channels if _norm_name(c.get("name", "")) in wanted]

    messages_by_channel: Dict[str, List[Dict[str, Any]]] = {}
    for ch in channels:
        cid = ch["id"]
        try:
            ch["members"] = list(client.paginate("conversations.members", "members", channel=cid, limit=200))
        except SlackError:
            ch.setdefault("members", [])
        seen: Dict[str, Dict[str, Any]] = {}
        roots = list(client.paginate("conversations.history", "messages", channel=cid, oldest=oldest, limit=200))
        for m in roots:
            seen[m["ts"]] = m
        # pull each thread's replies (root is returned again; dedup by ts)
        for m in roots:
            if m.get("thread_ts") == m.get("ts") and int(m.get("reply_count", 0) or 0) > 0:
                for rep in client.paginate("conversations.replies", "messages", channel=cid, ts=m["ts"], oldest=oldest, limit=200):
                    seen[rep["ts"]] = rep
        messages_by_channel[cid] = sorted(seen.values(), key=lambda x: float(x["ts"]))

    return {
        "workspace": workspace,
        "users": users,
        "channels": channels,
        "messages_by_channel": messages_by_channel,
    }


# --------------------------------------------------------------------- export writer


def _iso_day(ts: str) -> str:
    return datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime("%Y-%m-%d")


def _bucket_file(ch: Dict[str, Any]) -> str:
    if ch.get("is_im"):
        return "dms.json"
    if ch.get("is_mpim"):
        return "mpims.json"
    if ch.get("is_private"):
        return "groups.json"
    return "channels.json"


def write_export_dir(out: str, data: Dict[str, Any]) -> Dict[str, int]:
    """Write the standard Slack export layout that import_export() consumes:
    users.json, channels.json (+ groups/mpims/dms.json), <channel-name>/YYYY-MM-DD.json.
    Files hold raw Slack objects, unmodified, so ids/ts/thread_ts/reactions survive."""
    root = Path(out)
    root.mkdir(parents=True, exist_ok=True)
    (root / "users.json").write_text(json.dumps(data["users"], indent=1))

    buckets: Dict[str, List[Dict[str, Any]]] = {}
    for ch in data["channels"]:
        buckets.setdefault(_bucket_file(ch), []).append(ch)
    for fname, chans in buckets.items():
        (root / fname).write_text(json.dumps(chans, indent=1))

    n_msgs = 0
    for ch in data["channels"]:
        folder = root / (ch.get("name") or ch["id"]).replace("/", "_")
        msgs = data["messages_by_channel"].get(ch["id"], [])
        by_day: Dict[str, List[Dict[str, Any]]] = {}
        for m in msgs:
            by_day.setdefault(_iso_day(m["ts"]), []).append(m)
        if by_day:
            folder.mkdir(parents=True, exist_ok=True)
        for day, day_msgs in by_day.items():
            (folder / f"{day}.json").write_text(json.dumps(day_msgs, indent=1))
            n_msgs += len(day_msgs)

    return {
        "users": len(data["users"]),
        "channels": len(data["channels"]),
        "messages": n_msgs,
    }


# --------------------------------------------------------------------------- probe


def run_probe(client: SlackClient, sample_channel: Optional[str]) -> List[Dict[str, Any]]:
    """Exercise each needed method once and record ok / error (+ scope hint).
    This matrix is the 'flag if access is insufficient' core of the report."""
    matrix: List[Dict[str, Any]] = []
    sample_ts: Optional[str] = None
    for method, scope in PROBE_METHODS:
        params: Dict[str, Any] = {"limit": 1}
        if method == "auth.test":
            params = {}
        elif method == "conversations.list":
            params = {"limit": 1, "types": "public_channel"}
        elif method == "conversations.history":
            if not sample_channel:
                matrix.append({"method": method, "ok": None, "error": "skipped (no channel)", "scope": scope}); continue
            params = {"limit": 1, "channel": sample_channel}
        elif method == "conversations.replies":
            if not (sample_channel and sample_ts):
                matrix.append({"method": method, "ok": None, "error": "skipped (no thread)", "scope": scope}); continue
            params = {"limit": 1, "channel": sample_channel, "ts": sample_ts}
        elif method == "conversations.members":
            if not sample_channel:
                matrix.append({"method": method, "ok": None, "error": "skipped (no channel)", "scope": scope}); continue
            params = {"limit": 1, "channel": sample_channel}
        elif method == "search.messages":
            params = {"query": "the", "count": 1}
        try:
            j = client.ok_call(method, **params)
            if method == "conversations.history":
                msgs = j.get("messages") or []
                if msgs:
                    sample_ts = msgs[0].get("thread_ts") or msgs[0].get("ts")
            matrix.append({"method": method, "ok": True, "error": None, "scope": scope})
        except SlackError as e:
            needed = (e.payload.get("needed") or "")
            matrix.append({"method": method, "ok": False, "error": e.error, "needed": needed, "scope": scope})
        except Exception as e:  # network/other
            matrix.append({"method": method, "ok": False, "error": repr(e), "scope": scope})
    return matrix


# --------------------------------------------------------------------------- report


def build_report(probe: List[Dict[str, Any]], counts: Dict[str, int], data: Dict[str, Any],
                 *, since: str, stalls: int) -> Dict[str, Any]:
    by = {row["method"]: row for row in probe}
    auth_ok = by.get("auth.test", {}).get("ok") is True
    history_ok = by.get("conversations.history", {}).get("ok") is True
    users_ok = by.get("users.list", {}).get("ok") is True

    gaps: List[str] = []
    if by.get("search.messages", {}).get("ok") is False:
        gaps.append("search.messages denied -> no keyword harvest across the workspace.")
    if by.get("conversations.replies", {}).get("ok") is False:
        gaps.append("conversations.replies denied -> threads cannot be reconstructed.")
    # email present? (drives cross-clone identity linking)
    emails = sum(1 for u in data.get("users", []) if (u.get("profile") or {}).get("email"))
    if data.get("users") and emails == 0:
        gaps.append("no user emails (users:read.email missing) -> weaker cross-clone identity linking.")
    if counts.get("messages", 0) == 0 and history_ok:
        gaps.append("history readable but 0 messages in window -> widen --since or check channel membership.")

    sufficient = bool(auth_ok and history_ok and users_ok and counts.get("messages", 0) > 0)
    # date range actually reached
    all_ts = [float(m["ts"]) for msgs in data.get("messages_by_channel", {}).values() for m in msgs]
    span = None
    if all_ts:
        span = {
            "oldest": datetime.fromtimestamp(min(all_ts), tz=timezone.utc).isoformat(),
            "newest": datetime.fromtimestamp(max(all_ts), tz=timezone.utc).isoformat(),
        }
    return {
        "workspace": data.get("workspace", {}),
        "since": since,
        "counts": counts,
        "date_span": span,
        "rate_limit_stalls": stalls,
        "access_matrix": probe,
        "gaps": gaps,
        "sufficient_for_task_gen": sufficient,
        "verdict": (
            "SUFFICIENT for task-gen with this xoxp token."
            if sufficient
            else "INSUFFICIENT as-is -- see gaps; may need broader scopes or W-side access."
        ),
    }


def render_report_md(rep: Dict[str, Any]) -> str:
    lines = ["# Slack API export -- sufficiency report", ""]
    ws = rep["workspace"]
    lines.append(f"**Workspace:** {ws.get('name')} (`{ws.get('id')}`)  ")
    lines.append(f"**Window (`--since`):** {rep['since']}  ")
    if rep["date_span"]:
        lines.append(f"**Reached:** {rep['date_span']['oldest']} -> {rep['date_span']['newest']}  ")
    c = rep["counts"]
    lines.append(f"**Counts:** {c.get('channels',0)} channels, {c.get('users',0)} users, {c.get('messages',0)} messages  ")
    if rep["rate_limit_stalls"]:
        lines.append(f"**Rate-limit stalls:** {rep['rate_limit_stalls']}  ")
    lines += ["", "## Access matrix", "", "| method | ok | error | scope |", "|---|---|---|---|"]
    for row in rep["access_matrix"]:
        ok = "yes" if row["ok"] is True else ("no" if row["ok"] is False else "-")
        err = row.get("error") or ""
        if row.get("needed"):
            err += f" (needed: {row['needed']})"
        lines.append(f"| `{row['method']}` | {ok} | {err} | {row.get('scope') or ''} |")
    lines += ["", "## Gaps"]
    lines += ([f"- {g}" for g in rep["gaps"]] or ["- none"])
    lines += ["", f"## Verdict", "", f"**{rep['verdict']}**", ""]
    return "\n".join(lines)


# --------------------------------------------------------------------------- since


def parse_oldest(since: str) -> str:
    """`since` -> Slack `oldest` epoch-seconds string. Supports '90d','12h','all',
    or an ISO date 'YYYY-MM-DD'. Built to extend further back later."""
    s = since.strip().lower()
    if s in ("all", "0"):
        return "0"
    now = time.time()
    if s.endswith("d"):
        return f"{now - int(s[:-1]) * 86400:.6f}"
    if s.endswith("h"):
        return f"{now - int(s[:-1]) * 3600:.6f}"
    try:
        dt = datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return f"{dt.timestamp():.6f}"
    except ValueError:
        raise SystemExit(f"--since: unrecognized value {since!r} (use e.g. 90d, 12h, all, 2026-01-01)")


# --------------------------------------------------------------------------- CLI


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="spoink.slack_export", description="Read-only Slack export via the Web API (xoxp).")
    ap.add_argument("--channels", required=True, help="comma-separated channel names, e.g. '#eng,#incidents'")
    ap.add_argument("--since", default="90d", help="window: 90d | 12h | all | YYYY-MM-DD (default 90d)")
    ap.add_argument("--out", default="slack-export", help="export directory to write")
    ap.add_argument("--report", default=None, help="write sufficiency report (.md; .json alongside)")
    ap.add_argument("--token-env", default="SLACK_USER_TOKEN", help="env var holding the xoxp token")
    args = ap.parse_args(argv)

    token = os.environ.get(args.token_env)
    if not token:
        print(f"error: set {args.token_env} to an xoxp- user token (not passed on the CLI)", file=sys.stderr)
        return 2
    if not token.startswith("xoxp-"):
        print("warning: token does not start with 'xoxp-'; this tool targets a user token", file=sys.stderr)

    targets = [c for c in args.channels.split(",") if c.strip()]
    oldest = parse_oldest(args.since)
    client = SlackClient(token)
    try:
        data = fetch_workspace(client, targets, oldest)
        sample = data["channels"][0]["id"] if data["channels"] else None
        probe = run_probe(client, sample)
        counts = write_export_dir(args.out, data)
        rep = build_report(probe, counts, data, since=args.since, stalls=client.rate_limit_stalls)
    finally:
        client.close()

    print(json.dumps({"out": args.out, **counts, "sufficient": rep["sufficient_for_task_gen"]}))
    if args.report:
        md = args.report if args.report.endswith(".md") else args.report + ".md"
        Path(md).write_text(render_report_md(rep))
        Path(md[:-3] + ".json").write_text(json.dumps(rep, indent=2))
        print(f"report: {md}", file=sys.stderr)
    return 0 if rep["sufficient_for_task_gen"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

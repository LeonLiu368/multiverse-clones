"""slice_as_of(T): reconstruct a captured Slack export as of a point in time.

Time-travel primitive for the snapshot engine. Takes a standard Slack export dir
(what spoink.slack_export writes) and emits a new export dir containing only
messages with ts <= cutoff -- so it still round-trips through
abundant-slack-clone's import_export(). The user/channel roster is carried over
as-is (we don't have per-member join history; that's a later refinement).
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from .slack_export import _iso_day


def parse_tz(tz: str) -> timedelta:
    """'-7' | '-07:00' | '-0700' | '+5:30' -> timedelta."""
    tz = tz.strip()
    neg = tz.startswith("-")
    tz = tz.lstrip("+-")
    if ":" in tz:
        h, m = tz.split(":")
    elif len(tz) > 2:
        h, m = tz[:-2], tz[-2:]
    else:
        h, m = tz, "00"
    delta = timedelta(hours=int(h), minutes=int(m or 0))
    return -delta if neg else delta


def parse_cutoff(spec: str, tz: Optional[str]) -> float:
    """Resolve a cutoff to epoch seconds. Accepts an epoch, an ISO timestamp
    (with offset), or a tz-naive 'YYYY-MM-DD HH:MM[:SS]' paired with `tz`."""
    spec = spec.strip()
    try:
        return float(spec)
    except ValueError:
        pass
    try:
        dt = datetime.fromisoformat(spec.replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            return dt.timestamp()
        naive = dt.replace(tzinfo=None)
    except ValueError:
        naive = None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
            try:
                naive = datetime.strptime(spec, fmt)
                break
            except ValueError:
                continue
        if naive is None:
            raise SystemExit(f"--as-of: cannot parse {spec!r}")
    if tz is None:
        raise SystemExit("--as-of is timezone-naive; pass --tz (e.g. -7 for PDT, -8 for PST)")
    return naive.replace(tzinfo=timezone(parse_tz(tz))).timestamp()


def slice_export(in_dir: str, out_dir: str, cutoff: float) -> Dict[str, Any]:
    """Write a new export dir with only messages at-or-before `cutoff` (epoch s)."""
    root, out = Path(in_dir), Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for f in root.glob("*.json"):                 # roster (users/channels/groups/…)
        shutil.copy2(f, out / f.name)

    kept = dropped = 0
    last_kept: Optional[Dict[str, Any]] = None
    first_dropped: Optional[Dict[str, Any]] = None
    per_channel: Dict[str, int] = {}

    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        msgs = [m for day in sorted(folder.glob("*.json")) for m in json.load(open(day))]
        keep = [m for m in msgs if float(m["ts"]) <= cutoff]
        drop = [m for m in msgs if float(m["ts"]) > cutoff]
        kept += len(keep)
        dropped += len(drop)
        per_channel[folder.name] = len(keep)
        if keep:
            lk = max(keep, key=lambda m: float(m["ts"]))
            if last_kept is None or float(lk["ts"]) > float(last_kept["ts"]):
                last_kept = lk
        if drop:
            fd = min(drop, key=lambda m: float(m["ts"]))
            if first_dropped is None or float(fd["ts"]) < float(first_dropped["ts"]):
                first_dropped = fd
        if keep:
            od = out / folder.name
            od.mkdir(exist_ok=True)
            by_day: Dict[str, list] = {}
            for m in keep:
                by_day.setdefault(_iso_day(m["ts"]), []).append(m)
            for day, ms in by_day.items():
                json.dump(sorted(ms, key=lambda x: float(x["ts"])), open(od / f"{day}.json", "w"), indent=1)

    return {
        "cutoff_epoch": cutoff,
        "cutoff_utc": datetime.fromtimestamp(cutoff, tz=timezone.utc).isoformat(),
        "kept": kept,
        "dropped": dropped,
        "per_channel": per_channel,
        "last_kept": last_kept,
        "first_dropped": first_dropped,
    }


def _ts_epoch(iso: Optional[str]) -> Optional[float]:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _iso_z(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def slice_tracker(state: Dict[str, Any], cutoff: float) -> Dict[str, Any]:
    """Creation-cut a ticketvector / abundant-jira-clone state.json to <= cutoff (epoch s),
    in place: keep issues + comments created at-or-before T, drop later ones, recompute
    comments_count, and prune relations/links/attachments for dropped issues. `updated_at`
    is clamped to T so issues don't look edited in the future.

    NOTE: this is a CREATION-cut — kept issues still show their CURRENT state/labels/title.
    Faithful as-of-T field *state* needs the per-issue change log (Linear issueHistory),
    the same replay GitHub's --as-of does via the timeline; that's the follow-on.
    """
    kept, dropped = [], 0
    for i in state.get("issues", []):
        c = _ts_epoch(i.get("created_at"))
        if c is None or c <= cutoff:
            u = _ts_epoch(i.get("updated_at"))
            if u and u > cutoff:
                i["updated_at"] = _iso_z(cutoff)
            kept.append(i)
        else:
            dropped += 1
    kept_idents = {i["identifier"] for i in kept}

    out_comments: Dict[str, list] = {}
    c_kept = c_drop = 0
    for ident, lst in (state.get("comments") or {}).items():
        if ident not in kept_idents:
            c_drop += len(lst)
            continue
        keep = [c for c in lst if (_ts_epoch(c.get("created_at")) or 0) <= cutoff]
        c_kept += len(keep)
        c_drop += len(lst) - len(keep)
        if keep:
            out_comments[ident] = keep
    for i in kept:
        i["comments_count"] = len(out_comments.get(i["identifier"], []))

    state["issues"] = kept
    state["comments"] = out_comments
    for coll in ("relations", "links", "attachments"):
        if isinstance(state.get(coll), dict):
            state[coll] = {k: v for k, v in state[coll].items() if k in kept_idents}
    return {"issues_kept": len(kept), "issues_dropped": dropped,
            "comments_kept": c_kept, "comments_dropped": c_drop}


def _fmt(m: Optional[Dict[str, Any]]) -> str:
    if not m:
        return "—"
    when = datetime.fromtimestamp(float(m["ts"]), tz=timezone.utc).isoformat()
    return f"{when}  ({m['ts']})  {(' '.join((m.get('text') or '').split()))[:70]}"


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(prog="spoink.slice", description="Slice a captured corpus as of a point in time.")
    ap.add_argument("--kind", choices=["slack", "tracker"], default="slack",
                    help="slack = export dir; tracker = jira-clone state.json")
    ap.add_argument("--in", dest="in_dir", required=True, help="export dir (slack) or state.json (tracker)")
    ap.add_argument("--as-of", required=True, help="epoch | ISO w/ offset | 'YYYY-MM-DD HH:MM' (+ --tz)")
    ap.add_argument("--tz", default=None, help="offset for a tz-naive --as-of, e.g. -7 (PDT) or -8 (PST)")
    ap.add_argument("--out", required=True, help="output (sliced) export dir or state.json")
    args = ap.parse_args(argv)

    import sys
    cutoff = parse_cutoff(args.as_of, args.tz)
    if args.kind == "tracker":
        state = json.load(open(args.in_dir))
        res = slice_tracker(state, cutoff)
        json.dump(state, open(args.out, "w"), indent=2, ensure_ascii=False)
        print(json.dumps({"out": args.out, "cutoff_utc": _iso_z(cutoff), **res}))
        return 0
    res = slice_export(args.in_dir, args.out, cutoff)
    print(json.dumps({"out": args.out, "cutoff_utc": res["cutoff_utc"],
                      "kept": res["kept"], "dropped": res["dropped"]}))
    print(f"cutoff:        {res['cutoff_utc']}", file=sys.stderr)
    print(f"last kept:     {_fmt(res['last_kept'])}", file=sys.stderr)
    print(f"first dropped: {_fmt(res['first_dropped'])}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

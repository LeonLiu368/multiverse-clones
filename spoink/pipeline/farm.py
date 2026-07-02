"""Batch task farming — discover -> classify (archetype) -> generate -> validate -> probe -> rank.

Turns a live incident feed into a ranked TASK-BANK: each candidate is routed to its archetype
(code-fix / deployment / optimization / incident-response — diversity), shaped into a Harbor task
dir, run through the validation gates, and (for code archetypes) probed for buildability. Emits a
task-bank manifest grouped by archetype with an accept/reject reason per task, so you can farm at
scale and keep only the runnable, non-leaky ones.

    python -m spoink.pipeline.farm --feed github_revert --org abundant-ai --limit 10 --out task-bank
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import archetypes as A
from . import generate as gen
from . import harness
from . import spec as spc
from . import validate as V
from .discover import discover, to_dict

_ARCH_VALUE = {"incident_response": 1.0, "code_fix": 2.0, "deployment": 1.5, "optimization": 2.5}


def _rank(cand: Dict[str, Any], arch: A.Archetype, report: Dict[str, Any], probe: Dict[str, Any]) -> float:
    s = float(cand.get("score", 0)) + _ARCH_VALUE.get(arch.name, 1.0)
    if report.get("accepted"):
        s += 2
    if cand.get("resolution", {}).get("has_tests"):
        s += 2                                   # brings its own verifier
    if probe.get("ok"):
        s += 1
    if probe.get("built"):
        s += 2                                   # actually builds -> farmable now
    return round(s, 2)


def farm(feed: str, org: str, *, token: str, limit: int = 10, window_days: int = 120,
         out_dir: str = "task-bank", capture: bool = False, build_probe: bool = False) -> Dict[str, Any]:
    cands = discover(feed, token, org=org, window_days=window_days, max_candidates=limit)
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    tasks_dir = out / "tasks"; tasks_dir.mkdir(exist_ok=True)
    bank: List[Dict[str, Any]] = []

    for c in cands:
        cd = to_dict(c)
        arch = A.classify(cd)
        attached: List[Dict[str, Any]] = []
        # optionally capture the github SUT at T for code archetypes (heavy)
        if capture and arch.needs_code and "github" in (cd.get("required_data") or {}):
            try:
                from ..dashboard import sources as S
                run = tempfile.mkdtemp(prefix="spoink-farm-")
                S._capture_github(run, cd["required_data"]["github"])
                attached = [{"source": "github", "overlay": str(Path(run) / "snapshots")}]
            except Exception as e:  # noqa: BLE001
                attached = []; cd["_capture_error"] = str(e)[:160]

        spec = spc.spec_from_candidate(cd, attached, gateway_for={})
        res = gen.generate_task(spec, str(tasks_dir))
        bundle = str(Path(res["task_dir"]) / "environment" / "codebase.bundle")
        report = V.validate_task(
            res["task_dir"], bundle=bundle, resolution=cd.get("resolution", {}),
            overlays=[a["overlay"] for a in attached if a["source"] != "github"],
            changed_files=spec.changed_files, title=cd.get("title", ""),
            verifier_kind=spec.verifier.kind, f2p=spec.verifier.f2p).to_dict()
        probe = {}
        if arch.needs_code and Path(bundle).exists():
            probe = harness.probe_sut(bundle, cd.get("resolution", {}).get("base_sha", ""),
                                      spec.verifier.f2p, build=build_probe)

        reasons = [g["name"] for g in report["gates"] if g["status"] == "fail"]
        bank.append({
            "id": cd["id"], "archetype": arch.name, "kind": arch.kind, "grounds": arch.grounds,
            "verifier": spec.verifier.kind, "title": cd.get("title", ""), "t": cd.get("t"),
            "task_dir": res["task_dir"], "accepted": report["accepted"],
            "reject_reasons": reasons, "has_own_verifier": bool(cd.get("resolution", {}).get("has_tests")),
            "probe": {k: probe.get(k) for k in ("ok", "build_system", "built")} if probe else None,
            "rank": _rank(cd, arch, report, probe),
        })

    bank.sort(key=lambda b: -b["rank"])
    manifest = {"feed": feed, "org": org, "count": len(bank),
                "by_archetype": _tally(bank, "archetype"),
                "accepted": sum(1 for b in bank if b["accepted"]), "tasks": bank}
    (out / "task-bank.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def _tally(bank: List[Dict[str, Any]], key: str) -> Dict[str, int]:
    t: Dict[str, int] = {}
    for b in bank:
        t[b[key]] = t.get(b[key], 0) + 1
    return t


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Farm a ranked task-bank from an incident feed.")
    ap.add_argument("--feed", default="github_revert")
    ap.add_argument("--org", default="abundant-ai")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--window-days", type=int, default=120)
    ap.add_argument("--out", default="task-bank")
    ap.add_argument("--capture", action="store_true", help="capture the SUT snapshot per code task (heavy)")
    ap.add_argument("--build-probe", action="store_true", help="attempt the SUT build in the harness probe")
    a = ap.parse_args(argv)
    from .discover import FEED_ENV
    token = os.environ.get(FEED_ENV.get(a.feed, "GITHUB_TOKEN"), "")
    if not token:
        print(f"set {FEED_ENV.get(a.feed, 'GITHUB_TOKEN')}"); return 2
    m = farm(a.feed, a.org, token=token, limit=a.limit, window_days=a.window_days,
             out_dir=a.out, capture=a.capture, build_probe=a.build_probe)
    print(f"farmed {m['count']} -> {a.out}/task-bank.json")
    print(f"  by archetype: {m['by_archetype']}")
    print(f"  accepted: {m['accepted']}/{m['count']}")
    for b in m["tasks"][:10]:
        pv = "" if not b["probe"] else f" probe={b['probe'].get('build_system')}/{b['probe'].get('ok')}"
        print(f"  [{b['rank']:>4}] {b['archetype']:<17} {b['verifier']:<12} "
              f"{'OK ' if b['accepted'] else 'rej'} {b['title'][:44]}{pv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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


def _ensure_bundle(repo: str, token: str, snaps_root: Path, done: set) -> bool:
    """Mirror-clone a repo ONCE into a shared snapshots dir (git.bundle only — no full snapshot).
    Reused across every candidate from that repo: the big throughput win, since a feed is usually
    dominated by one repo."""
    import subprocess
    if repo in done:
        return True
    d = snaps_root / repo.replace("/", "__"); d.mkdir(parents=True, exist_ok=True)
    src = f"https://{token + '@' if token else ''}github.com/{repo}.git"
    mir = d / "_mirror.git"
    if not (d / "git.bundle").exists():
        if subprocess.run(["git", "clone", "--quiet", "--mirror", src, str(mir)],
                          capture_output=True, text=True).returncode != 0:
            return False
        subprocess.run(["git", "-C", str(mir), "bundle", "create", str((d / "git.bundle").resolve()), "--all"],
                       capture_output=True, text=True)
    done.add(repo)
    return (d / "git.bundle").exists()


def farm(feed: str, org: str, *, token: str, limit: int = 10, window_days: int = 120,
         out_dir: str = "task-bank", capture: bool = False, build_probe: bool = False,
         promote: bool = False, promote_cap: int = 6) -> Dict[str, Any]:
    cands = discover(feed, token, org=org, window_days=window_days, max_candidates=limit)
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    tasks_dir = out / "tasks"; tasks_dir.mkdir(exist_ok=True)
    snaps_root = Path(tempfile.mkdtemp(prefix="spoink-farm-snaps-"))   # one shared SUT bundle cache
    bundle_done: set = set()
    bank: List[Dict[str, Any]] = []
    n_promoted = 0

    for c in cands:
        cd = to_dict(c)
        arch = A.classify(cd)
        attached: List[Dict[str, Any]] = []
        # lightweight SUT capture: one shared git.bundle per repo (not a per-candidate full snapshot)
        if capture and arch.needs_code and "github" in (cd.get("required_data") or {}):
            repo = (cd.get("resolution") or {}).get("repo", "")
            if repo and _ensure_bundle(repo, token, snaps_root, bundle_done):
                attached = [{"source": "github", "overlay": str(snaps_root)}]
            else:
                cd["_capture_error"] = f"bundle failed for {repo}"

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

        # THROUGHPUT PROOF: actually prove the task (docker nop=0/oracle=1), capped to keep it tractable
        promo = None
        if (promote and report["accepted"] and spec.verifier.kind == "pytest_pr"
                and Path(bundle).exists() and n_promoted < promote_cap):
            from . import promote as P
            n_promoted += 1
            pr = P.promote(res["task_dir"], timeout=1500)
            promo = {"status": pr.get("status"), "nop": pr.get("nop_exit"), "oracle": pr.get("oracle_exit"),
                     "detail": pr.get("detail", "")[:120]}

        reasons = [g["name"] for g in report["gates"] if g["status"] == "fail"]
        bank.append({
            "id": cd["id"], "archetype": arch.name, "kind": arch.kind, "grounds": arch.grounds,
            "verifier": spec.verifier.kind, "title": cd.get("title", ""), "t": cd.get("t"),
            "task_dir": res["task_dir"], "accepted": report["accepted"],
            "reject_reasons": reasons, "has_own_verifier": bool(cd.get("resolution", {}).get("has_tests")),
            "probe": {k: probe.get(k) for k in ("ok", "build_system", "built")} if probe else None,
            "promote": promo, "proven": bool(promo and promo.get("status") == "proven"),
            "rank": _rank(cd, arch, report, probe) + (3 if promo and promo.get("status") == "proven" else 0),
        })

    import shutil
    shutil.rmtree(snaps_root, ignore_errors=True)
    bank.sort(key=lambda b: -b["rank"])
    manifest = {"feed": feed, "org": org, "count": len(bank),
                "by_archetype": _tally(bank, "archetype"),
                "accepted": sum(1 for b in bank if b["accepted"]),
                "proven": sum(1 for b in bank if b.get("proven")), "tasks": bank}
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
    ap.add_argument("--capture", action="store_true", help="capture the SUT bundle (shared per repo)")
    ap.add_argument("--build-probe", action="store_true", help="attempt the SUT build in the harness probe")
    ap.add_argument("--promote", action="store_true", help="docker nop=0/oracle=1 on accepted code tasks")
    ap.add_argument("--promote-cap", type=int, default=6, help="max tasks to promote (each is a real build)")
    a = ap.parse_args(argv)
    from .discover import FEED_ENV
    token = os.environ.get(FEED_ENV.get(a.feed, "GITHUB_TOKEN"), "")
    if not token:
        print(f"set {FEED_ENV.get(a.feed, 'GITHUB_TOKEN')}"); return 2
    m = farm(a.feed, a.org, token=token, limit=a.limit, window_days=a.window_days,
             out_dir=a.out, capture=a.capture, build_probe=a.build_probe,
             promote=a.promote, promote_cap=a.promote_cap)
    print(f"farmed {m['count']} -> {a.out}/task-bank.json")
    print(f"  by archetype: {m['by_archetype']}")
    print(f"  accepted: {m['accepted']}/{m['count']}  |  proven: {m.get('proven', 0)}")
    for b in m["tasks"][:12]:
        pv = "" if not b["probe"] else f" build={b['probe'].get('build_system')}"
        pm = f" PROVEN(nop={b['promote']['nop']},oracle={b['promote']['oracle']})" if b.get("proven") else (
              f" promote={b['promote']['status']}" if b.get("promote") else "")
        print(f"  [{b['rank']:>4}] {b['archetype']:<16} {b['verifier']:<12} "
              f"{'OK ' if b['accepted'] else 'rej'} {b['title'][:40]}{pv}{pm}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

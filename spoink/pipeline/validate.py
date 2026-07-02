"""Task validation gates — the quality bar every generated task must clear.

Encodes the clone-task-builder non-negotiables so we can generate *strong* tasks, not just tasks:
  1. Harbor contract      — task.toml/compose/test.sh structurally correct (custom_docker_compose,
                            no `networks:`, healthchecks, linux/amd64, reward.txt).
  2. Code cut (leakage)   — the shipped SUT bundle must NOT contain the fix commit; an agent that
                            `git log`s the bundle can't read the answer. THE critical code gate.
  3. Surface leakage      — the answer (fix PR #, fix sha, changed files, title keywords) must be
                            absent from every served overlay (Slack/Linear/Logfire captured < T).
  4. Verifier grounding   — the verifier is tied to the real fix (changed test files exist for
                            pytest_pr; a grader for module_check). Empirical F2P/P2P is confirmed at
                            task BUILD (derive_pr_verifier), where the env exists.

Gates are cheap + reliable (git plumbing + grep — no pytest at gen time). A task is ACCEPTED only if
no CRITICAL gate fails; non-critical gates may warn/skip.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

CRITICAL = {"contract", "code_cut", "surface_leakage"}


@dataclass
class Gate:
    name: str
    status: str                          # "pass" | "fail" | "warn" | "skip"
    detail: str = ""
    evidence: List[str] = field(default_factory=list)


@dataclass
class Report:
    gates: List[Gate] = field(default_factory=list)

    @property
    def accepted(self) -> bool:
        return not any(g.status == "fail" and g.name in CRITICAL for g in self.gates)

    def to_dict(self) -> Dict[str, Any]:
        return {"accepted": self.accepted,
                "gates": [{"name": g.name, "status": g.status, "detail": g.detail,
                           "evidence": g.evidence[:8]} for g in self.gates]}


def _git(*args, cwd=None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


# ------------------------------------------------------------------ individual gates
def contract_lint(task_dir: str) -> Gate:
    root = Path(task_dir)
    problems: List[str] = []
    toml = (root / "task.toml").read_text() if (root / "task.toml").exists() else ""
    if "custom_docker_compose" not in toml:
        problems.append("task.toml missing custom_docker_compose")
    compose = ""
    for cf in ("environment/docker-compose.yaml", "environment/docker-compose.yml"):
        if (root / cf).exists():
            compose = (root / cf).read_text(); break
    if not compose:
        problems.append("no docker-compose in environment/")
    else:
        if re.search(r"^\s*networks:", compose, re.M):
            problems.append("compose declares `networks:` (forbidden on Harbor/Oddish)")
        if "linux/amd64" not in compose:
            problems.append("compose missing platform: linux/amd64")
        if "healthcheck" not in compose:
            problems.append("compose has no healthcheck (depends_on can't gate)")
    ts = root / "tests" / "test.sh"
    if not ts.exists():
        problems.append("tests/test.sh missing")
    elif "reward.txt" not in ts.read_text():
        problems.append("tests/test.sh never writes reward.txt")
    if not (root / "solution" / "solve.sh").exists():
        problems.append("solution/solve.sh missing (no oracle)")
    return Gate("contract", "fail" if problems else "pass",
                "; ".join(problems) or "Harbor structure OK", problems)


def code_cut(bundle: str, head_sha: str) -> Gate:
    """The shipped SUT bundle must NOT contain the fix commit (else the agent can read the answer)."""
    if not bundle or not Path(bundle).exists():
        return Gate("code_cut", "skip", "no SUT bundle shipped")
    if not head_sha:
        return Gate("code_cut", "warn", "no head_sha to check against")
    heads = _git("bundle", "list-heads", bundle)
    # does the bundle's history reach the fix? clone --mirror the bundle + check membership
    import tempfile
    tmp = tempfile.mkdtemp(prefix="spoink-cut-")
    try:
        cl = _git("clone", "--quiet", "--mirror", bundle, tmp)
        if cl.returncode != 0:
            return Gate("code_cut", "warn", f"couldn't inspect bundle: {cl.stderr[-160:]}")
        cat = _git("cat-file", "-t", head_sha, cwd=tmp)
        if cat.returncode == 0:   # fix object is present -> LEAK
            return Gate("code_cut", "fail",
                        f"fix commit {head_sha[:12]} is reachable in the shipped bundle — "
                        "slice history to the incident tip", [head_sha])
        return Gate("code_cut", "pass", f"fix {head_sha[:12]} excluded from the SUT bundle")
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


def _answer_tokens(resolution: Dict[str, Any], changed_files: List[str], title: str) -> List[str]:
    toks: List[str] = []
    if resolution.get("pr"):
        toks.append(f"#{resolution['pr']}")
    for k in ("head_sha", "merge_commit_sha"):
        if resolution.get(k):
            toks.append(resolution[k][:12])
    toks += [Path(f).name for f in (changed_files or [])]            # fix'd file basenames
    toks += [w for w in re.findall(r"[A-Za-z0-9_]{5,}", title or "")   # distinctive title words
             if w.lower() not in _STOP][:6]
    # dedupe, keep non-trivial
    seen, out = set(), []
    for t in toks:
        t = t.strip()
        if len(t) >= 4 and t.lower() not in seen:
            seen.add(t.lower()); out.append(t)
    return out


_STOP = {"revert", "fix", "hotfix", "patch", "update", "changes", "should", "which", "there"}


def surface_leakage(overlays: List[str], resolution: Dict[str, Any],
                    changed_files: List[str], title: str) -> Gate:
    """The answer must not already be written in the served surfaces (they're captured < T)."""
    tokens = _answer_tokens(resolution, changed_files, title)
    if not tokens:
        return Gate("surface_leakage", "warn", "no answer tokens to check")
    hits: List[str] = []
    for ov in overlays:
        p = Path(ov)
        files = [p] if p.is_file() else [f for f in p.rglob("*") if f.is_file()]
        for f in files:
            # skip code + git internals (the SUT is checked by code_cut) and binaries
            if (f.suffix in (".bundle", ".pack", ".idx", ".gz", ".png", ".jpg")
                    or "_mirror.git" in f.parts or ".git" in f.parts):
                continue
            try:
                text = f.read_text(errors="ignore")
            except Exception:
                continue
            for t in tokens:
                if t in text:
                    hits.append(f"{f.name}: '{t}'")
    if hits:
        return Gate("surface_leakage", "fail",
                    f"answer leaked into {len(hits)} place(s) — capture the surface strictly before T",
                    hits)
    return Gate("surface_leakage", "pass", f"no answer tokens in served surfaces ({len(tokens)} checked)")


def verifier_grounding(verifier_kind: str, f2p: List[str], has_tests: bool,
                       grader_present: bool = False) -> Gate:
    if verifier_kind == "pytest_pr":
        if f2p:
            return Gate("verifier", "pass",
                        f"{len(f2p)} changed test file(s) target the fix; exact F2P/P2P derived at build")
        if has_tests:
            return Gate("verifier", "warn", "PR shipped tests but none were identified as F2P targets")
        return Gate("verifier", "fail",
                    "pytest_pr but no test files and no F2P target — nothing to grade (oracle can't reach reward=1)")
    if verifier_kind == "module_check":
        # module_check needs a bespoke grader that prints reward=0/1. Without tests/grade.py the
        # verifier calls a nonexistent script and EVERY grade (incl. the oracle) returns reward=0 —
        # the task is unverifiable. This is a hard fail, not a warning.
        if grader_present:
            return Gate("verifier", "pass", "module_check with a bespoke grader (tests/grade.py) present")
        return Gate("verifier", "fail",
                    "module_check has no grader (tests/grade.py) — the fix can't be verified; author a grader "
                    "or skip candidates whose PR shipped no test")
    return Gate("verifier", "warn", f"unrecognized verifier kind {verifier_kind!r}")


# ------------------------------------------------------------------ top-level
def validate_task(task_dir: str, *, bundle: str = "", resolution: Optional[Dict[str, Any]] = None,
                  overlays: Optional[List[str]] = None, changed_files: Optional[List[str]] = None,
                  title: str = "", verifier_kind: str = "", f2p: Optional[List[str]] = None) -> Report:
    resolution = resolution or {}
    rep = Report()
    rep.gates.append(contract_lint(task_dir))
    rep.gates.append(code_cut(bundle, resolution.get("head_sha", "")))
    rep.gates.append(surface_leakage(overlays or [], resolution, changed_files or [], title))
    grader_present = (Path(task_dir) / "tests" / "grade.py").exists()
    rep.gates.append(verifier_grounding(verifier_kind, f2p or [], bool(resolution.get("has_tests")),
                                        grader_present=grader_present))
    return rep

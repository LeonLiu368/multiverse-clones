"""TaskSpec — the recipe a generated task is built from.

A spec names: the incident moment T, the evidence SURFACES (each a captured/sliced overlay +
the gateway image that serves it), the optional code ANCHOR (the SUT as a git bundle at the
incident tip), the agent INSTRUCTION, and the VERIFIER strategy. `generate_task(spec, out)`
turns it into a runnable task dir + manifest (see generate.py)."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_T = "2026-06-25T00:34:00Z"


@dataclass
class Surface:
    """One evidence sidecar: a clone gateway serving a captured overlay."""
    source: str                       # slack | linear | logfire | gauge | github
    overlay: str                      # path to the run artifact (export dir / state.json / records.json / snapshots)
    gateway_image: str                # the baked per-incident gateway image (don't consolidate — bake)
    hostname: str = ""                # defaults to a sensible per-source name

    def __post_init__(self):
        self.hostname = self.hostname or {"linear": "jira"}.get(self.source, self.source)


@dataclass
class Anchor:
    """The SUT: a git bundle sliced to the incident tip (history up to T, fix excluded)."""
    bundle: str                       # path to codebase.bundle
    commit: str                       # the incident-tip sha to check out
    backend_subdir: str = "backend"   # where the app (uv sync target) lives inside the repo
    workdir: str = "/app"


@dataclass
class VerifierSpec:
    """How reward is computed. Two idioms (clone-task-builder):
      * observability code-fix  -> run a test suite (F2P/P2P derived from the resolution PR),
        or a bespoke `module_check` smoke when the PR shipped no test.
      * integration             -> read final state back through the clone CLIs (`readback`)."""
    kind: str                         # "pytest_pr" | "module_check" | "readback"
    # pytest_pr: tests that must pass at head (fail at base). Derived by verifier.derive_pr_verifier.
    f2p: List[str] = field(default_factory=list)
    p2p: List[str] = field(default_factory=list)
    test_cmd: str = "python -m pytest -q"
    # module_check: a standalone grader script (path) copied into tests/ and run in the SUT venv.
    grader_script: str = ""
    # readback: assertions run through the agent's CLIs; each {cli, expect_substr|expect_json}
    checks: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class TaskSpec:
    name: str                         # "oddish-incident/preview-500s"
    kind: str                         # "observability" | "integration"
    incident_t: str
    instruction: str
    surfaces: List[Surface]
    verifier: VerifierSpec
    anchor: Optional[Anchor] = None
    source_repo: str = ""
    fixed_by_pr: str = ""
    broke_in_pr: str = ""
    agents: List[Dict[str, Any]] = field(default_factory=lambda: [
        {"name": "nop"}, {"name": "oracle"},
        {"name": "gemini-cli", "model_name": "google/gemini-3.1-pro-preview", "n_trials": 2},
        {"name": "codex", "model_name": "openai/gpt-5.5", "n_trials": 2},
    ])
    # the oracle's actions: a shell snippet that fixes the code / drives the tools (the agent has the same CLIs)
    oracle_steps: str = ""
    changed_files: List[str] = field(default_factory=list)   # files the fix touched (for verifier + leakage audit)
    fix_patch: str = ""                                       # the resolution diff (base..head) = the oracle

    def slug(self) -> str:
        return self.name.split("/")[-1]


def spec_from_runs(name: str, kind: str, incident_t: str, instruction: str,
                   runs: List[Dict[str, Any]], gateway_for: Dict[str, str],
                   verifier: VerifierSpec, anchor: Optional[Anchor] = None,
                   **meta) -> TaskSpec:
    """Build a TaskSpec from dashboard run records. `runs` are the run dicts (with .source and a
    resolved overlay path); `gateway_for` maps a source -> its baked gateway image tag."""
    surfaces = []
    for r in runs:
        src = r["source"]
        surfaces.append(Surface(source=src, overlay=r["overlay"],
                                 gateway_image=gateway_for[src]))
    return TaskSpec(name=name, kind=kind, incident_t=incident_t, instruction=instruction,
                    surfaces=surfaces, verifier=verifier, anchor=anchor, **meta)


def spec_from_candidate(cand: Dict[str, Any], attached: List[Dict[str, Any]],
                        gateway_for: Dict[str, str], instruction: str = "") -> TaskSpec:
    """Turn a discovered Candidate (+ its attached snapshot runs) into a TaskSpec.

    - surfaces  = the attached runs (each a captured overlay + its baked gateway image)
    - anchor    = the github snapshot's git.bundle @ the incident-tip (resolution.base_sha)
    - verifier  = ADAPTIVE: pytest_pr (F2P from the PR's tests) if the fix shipped tests, else module_check
    The resolution refs are carried through so a build step can derive exact F2P/P2P (verifier.derive_pr_verifier).
    """
    res = cand.get("resolution", {})
    repo = res.get("repo", "")
    slug = (repo.split("/")[-1] or "incident") + "-" + cand["id"].split("-")[-1]
    surfaces = [Surface(source=r["source"], overlay=r["overlay"],
                        gateway_image=gateway_for.get(r["source"], f"ghcr.io/abundant-ai/{r['source']}-gateway:TODO"))
                for r in attached]

    anchor = None
    changed, changed_tests, patch = [], [], ""
    gh = next((r for r in attached if r["source"] == "github"), None)
    if gh and res.get("base_sha"):
        full = Path(gh["overlay"]) / repo.replace("/", "__") / "git.bundle"
        # slice the SUT to the incident tip (fix EXCLUDED) + read the fix's changed files + the fix
        # PATCH (the oracle) from the full mirror — served bundle must not contain the answer (non-neg #2)
        sliced, changed, patch = _prepare_sut(full, res["base_sha"], res.get("head_sha", ""))
        changed_tests = [f for f in changed if re.search(r"(^|/)tests?/|_test\.|test_.*\.py|\.test\.", f)]
        anchor = Anchor(bundle=str(sliced or full), commit=res["base_sha"])

    if res.get("has_tests"):
        verifier = VerifierSpec(kind="pytest_pr", f2p=changed_tests)  # exact F2P/P2P derived at build
    else:
        verifier = VerifierSpec(kind="module_check", grader_script="")

    return TaskSpec(
        name=f"spoink-incidents/{slug}", kind="observability",
        incident_t=cand.get("t", DEFAULT_T),
        instruction=instruction or _default_instruction(cand),
        surfaces=surfaces, verifier=verifier, anchor=anchor, changed_files=changed, fix_patch=patch,
        source_repo=repo, fixed_by_pr=f"#{res.get('pr')}" if res.get("pr") else "",
        oracle_steps=(f"# resolution: {repo}#{res.get('pr')} "
                      f"base={res.get('base_sha','')[:12]} head={res.get('head_sha','')[:12]}\n"))


def _prepare_sut(full_bundle: Path, base_sha: str, head_sha: str):
    """From the snapshot's full mirror bundle, produce (sliced_bundle_at_base, changed_files, fix_patch).
    Slicing excludes the fix from the shipped SUT; the diff/patch feed the verifier, leakage audit,
    and the oracle (solution/fix.patch)."""
    import shutil
    import subprocess
    import tempfile
    if not full_bundle.exists():
        return None, [], ""
    tmp = tempfile.mkdtemp(prefix="spoink-sut-")
    changed: List[str] = []
    patch = ""
    try:
        if subprocess.run(["git", "clone", "--quiet", "--mirror", str(full_bundle), tmp],
                          capture_output=True, text=True).returncode != 0:
            return None, [], ""
        if head_sha:
            d = subprocess.run(["git", "-C", tmp, "diff", "--name-only", f"{base_sha}..{head_sha}"],
                               capture_output=True, text=True)
            if d.returncode == 0:
                changed = [ln for ln in d.stdout.splitlines() if ln.strip()]
            p = subprocess.run(["git", "-C", tmp, "diff", f"{base_sha}..{head_sha}"],
                               capture_output=True, text=True)
            if p.returncode == 0:
                patch = p.stdout
        sliced = full_bundle.with_name("git.sliced.bundle")
        # a bare sha isn't a ref, and `git bundle` needs refs — point a branch at the incident tip,
        # then bundle history reachable from it (the fix commit is NOT included)
        subprocess.run(["git", "-C", tmp, "branch", "-f", "incident-tip", base_sha],
                       capture_output=True, text=True)
        if subprocess.run(["git", "-C", tmp, "bundle", "create", str(sliced.resolve()), "incident-tip"],
                          capture_output=True, text=True).returncode == 0:
            return sliced, changed, patch
        return None, changed, patch
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _default_instruction(cand: Dict[str, Any]) -> str:
    return (f"Something is broken in production. Investigate the available surfaces "
            f"(telemetry, chat, the codebase) and fix the underlying bug.\n\n"
            f"Incident: {cand.get('title','')}\n")


def load_spec(path: str) -> TaskSpec:
    d = json.loads(Path(path).read_text())
    d["surfaces"] = [Surface(**s) for s in d.get("surfaces", [])]
    d["verifier"] = VerifierSpec(**d["verifier"])
    if d.get("anchor"):
        d["anchor"] = Anchor(**d["anchor"])
    return TaskSpec(**d)

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
    # infra sidecars the SUT/tests need to actually run (real backend/DevOps incidents need a DB, cache,
    # etc.). infra = service names to add to the compose; infra_env = vars wired onto `main` at runtime.
    infra: List[str] = field(default_factory=list)
    infra_env: Dict[str, str] = field(default_factory=dict)

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
    changed, changed_tests, patch, test_src = [], [], "", ""
    gh = next((r for r in attached if r["source"] == "github"), None)
    if gh and res.get("base_sha"):
        full = Path(gh["overlay"]) / repo.replace("/", "__") / "git.bundle"
        # slice the SUT to the incident tip (fix EXCLUDED) + read the fix's changed files + the fix
        # PATCH (the oracle) from the full mirror — served bundle must not contain the answer (non-neg #2)
        sliced, changed, patch, subdir, test_src = _prepare_sut(full, res["base_sha"], res.get("head_sha", ""))
        # test targets, made relative to the detected build root so pytest runs from there
        pref = subdir + "/" if subdir else ""
        changed_tests = [f[len(pref):] if f.startswith(pref) else f
                         for f in changed if re.search(r"(^|/)tests?/|_test\.|test_.*\.py|\.test\.", f)]
        # narrow to the test FUNCTIONS the PR added — running the whole file drags in unrelated
        # pre-existing tests that can fail in a minimal env and sink the oracle
        changed_tests = _added_test_nodes(patch, changed_tests, subdir) or changed_tests
        anchor = Anchor(bundle=str(sliced or full), commit=res["base_sha"], backend_subdir=subdir)
    infra, infra_env = _detect_infra(patch + "\n" + test_src)

    # the archetype gives this incident its task shape: instruction + verifier + kind (diversity)
    from . import archetypes as A
    arch = A.classify(cand)
    vkind = arch.verifier_kind
    if vkind == "pytest_pr" and not res.get("has_tests"):
        vkind = "module_check"                                   # code fix that shipped no tests
    verifier = VerifierSpec(kind=vkind, f2p=changed_tests)       # f2p doubles as the regression guard

    # NEVER put the PR title in the agent-facing instruction — it usually DESCRIBES the fix (leakage).
    # Give a fair, non-leaky target instead: the failing tests (SWE-style) when there's no evidence
    # surface to carry a symptom; otherwise stay symptom-level and let the surfaces hide the clue.
    has_surface = any(s.source in ("slack", "linear", "logfire") for s in surfaces)
    if instruction:
        instr = instruction
    elif vkind == "pytest_pr" and changed_tests and not has_surface:
        instr = arch.instruction + "\n\nMake these currently-failing tests pass without breaking others:\n  " \
                + "\n  ".join(changed_tests)
    else:
        instr = arch.instruction + f"\n\n(incident in {repo} around {cand.get('t','')[:10]})\n"

    return TaskSpec(
        name=f"spoink-{arch.name}/{slug}", kind=arch.kind,
        incident_t=cand.get("t", DEFAULT_T),
        instruction=instr,
        surfaces=surfaces, verifier=verifier, anchor=anchor, changed_files=changed, fix_patch=patch,
        infra=infra, infra_env=infra_env,
        source_repo=repo, fixed_by_pr=f"#{res.get('pr')}" if res.get("pr") else "",
        oracle_steps=(f"# archetype: {arch.name} ({arch.grounds})\n"
                      f"# resolution: {repo}#{res.get('pr')} "
                      f"base={res.get('base_sha','')[:12]} head={res.get('head_sha','')[:12]}\n"))


# the env var a test reads for its DB DSN (ODDISH_DATABASE_URL, DATABASE_URL, TEST_DATABASE_URL, ...)
_DBURL_VAR = re.compile(r"""(?:environ\.get|getenv|environ\[)\(?["']([A-Z][A-Z0-9_]*DATABASE_URL[A-Z0-9_]*)["']""")


def _detect_infra(patch: str):
    """Detect infra sidecars the SUT/tests need from the fix patch (which includes the changed test
    files). Real backend/DevOps fixes exercise a real DB — without it the test SKIPS or ERRORS and the
    task is ungradeable. Returns (infra_services, main_env). Postgres for now; extendable to redis, etc."""
    infra: List[str] = []
    env: Dict[str, str] = {}
    text = patch or ""
    if any(m in text for m in ("postgresql", "asyncpg", "psycopg", "create_async_engine")) or "DATABASE_URL" in text:
        infra.append("postgres")
        m = _DBURL_VAR.search(text)
        var = m.group(1) if m else "DATABASE_URL"
        # asyncpg driver iff the test uses the async engine (this repo does); else the sync psycopg URL
        drv = "postgresql+asyncpg" if ("asyncpg" in text or "create_async_engine" in text) else "postgresql"
        env[var] = f"{drv}://spoink:spoink@postgres:5432/spoink"
    return infra, env


def _added_test_nodes(patch: str, changed_tests: List[str], subdir: str) -> List[str]:
    """From the fix patch, produce pytest NODE ids for the test functions the PR added/changed
    (e.g. `tests/test_x.py::test_new`). Falls back to the whole file when no added `def test_*`
    is visible. `changed_tests` are build-root-relative; the patch paths are repo-relative."""
    added: Dict[str, List[str]] = {}
    cur = None
    for ln in patch.splitlines():
        if ln.startswith("+++ b/"):
            cur = ln[6:].strip()
        elif ln.startswith("+") and not ln.startswith("+++") and cur:
            m = re.search(r"\bdef (test_\w+)", ln)
            if m:
                added.setdefault(cur, []).append(m.group(1))
    pref = subdir + "/" if subdir else ""
    nodes: List[str] = []
    for t in changed_tests:                                  # build-root-relative
        funcs = list(dict.fromkeys(added.get(pref + t, [])))  # repo-relative key
        nodes += [f"{t}::{fn}" for fn in funcs] if funcs else [t]
    return nodes


def _prepare_sut(full_bundle: Path, base_sha: str, head_sha: str):
    """From the snapshot's full mirror bundle, produce (sliced_bundle_at_base, changed_files, fix_patch).
    Slicing excludes the fix from the shipped SUT; the diff/patch feed the verifier, leakage audit,
    and the oracle (solution/fix.patch)."""
    import shutil
    import subprocess
    import tempfile
    if not full_bundle.exists():
        return None, [], "", "", ""
    tmp = tempfile.mkdtemp(prefix="spoink-sut-")
    changed: List[str] = []
    patch, subdir, test_src = "", "", ""
    try:
        if subprocess.run(["git", "clone", "--quiet", "--mirror", str(full_bundle), tmp],
                          capture_output=True, text=True).returncode != 0:
            return None, [], "", "", ""
        if head_sha:
            d = subprocess.run(["git", "-C", tmp, "diff", "--name-only", f"{base_sha}..{head_sha}"],
                               capture_output=True, text=True)
            if d.returncode == 0:
                changed = [ln for ln in d.stdout.splitlines() if ln.strip()]
            p = subprocess.run(["git", "-C", tmp, "diff", f"{base_sha}..{head_sha}"],
                               capture_output=True, text=True)
            if p.returncode == 0:
                patch = p.stdout
            # read the FULL changed test files at head (not just diff context) so infra detection
            # (e.g. the DATABASE_URL var a skipif reads) is reliable even when that line is unchanged
            for f in changed:
                if re.search(r"(^|/)tests?/|_test\.|test_.*\.py", f):
                    s = subprocess.run(["git", "-C", tmp, "show", f"{head_sha}:{f}"],
                                       capture_output=True, text=True)
                    if s.returncode == 0:
                        test_src += s.stdout + "\n"
        # detect the build root: the top-level dir the fix touches that carries a python manifest.
        # A fix often also touches ancillary tops (.github CI, docs) — those must NOT defeat detection,
        # so we skip dotdirs and consider EVERY changed top, keeping the one(s) with a manifest.
        tops = [t for t in {f.split("/")[0] for f in changed if "/" in f} if not t.startswith(".")]
        manifest_tops = []
        for top in tops:
            ls = subprocess.run(["git", "-C", tmp, "ls-tree", "--name-only", f"{base_sha}", f"{top}/"],
                                capture_output=True, text=True)
            if any(m in ls.stdout for m in ("pyproject.toml", "uv.lock", "setup.py", "requirements.txt")):
                manifest_tops.append(top)
        if len(manifest_tops) == 1:
            subdir = manifest_tops[0]
        elif len(manifest_tops) > 1:
            # multiple python roots touched — prefer the one holding the PR's changed test files
            test_tops = {f.split("/")[0] for f in changed
                         if re.search(r"(^|/)tests?/|_test\.|test_.*\.py", f)}
            inter = [t for t in manifest_tops if t in test_tops]
            subdir = (inter or sorted(manifest_tops))[0]
        sliced = full_bundle.with_name("git.sliced.bundle")
        # a bare sha isn't a ref, and `git bundle` needs refs — point a branch at the incident tip,
        # then bundle history reachable from it (the fix commit is NOT included)
        subprocess.run(["git", "-C", tmp, "branch", "-f", "incident-tip", base_sha],
                       capture_output=True, text=True)
        if subprocess.run(["git", "-C", tmp, "bundle", "create", str(sliced.resolve()), "incident-tip"],
                          capture_output=True, text=True).returncode == 0:
            return sliced, changed, patch, subdir, test_src
        return None, changed, patch, subdir, test_src
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

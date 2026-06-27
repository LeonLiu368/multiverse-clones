"""Verifier derivation (#5). Two idioms, per clone-task-builder:

  * OBSERVABILITY code-fix — grade by running a test suite:
      - `pytest_pr`: F2P/P2P tests derived EMPIRICALLY from the resolution PR (run the suite at
        base and head; keep tests that fail@base and pass@head). reward=1 iff they pass.
      - `module_check`: a bespoke smoke (e.g. configure_mappers) when the PR shipped no test —
        a standalone grader copied into tests/ that prints `reward=1`.
  * INTEGRATION — grade by reading final state back THROUGH the agent's CLIs (`readback`):
        each check runs a clone CLI and asserts on the output (substring or a python predicate).

`render_verifier(spec)` returns (test.sh, {extra files}). `derive_pr_verifier(...)` is the
build-time helper that computes F2P/P2P by actually running the suite at two commits.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple

from .spec import TaskSpec

_HEAD = "#!/usr/bin/env bash\nset -uo pipefail\nmkdir -p /logs/verifier 2>/dev/null || true\nHERE=\"$(cd \"$(dirname \"$0\")\" && pwd)\"\n"
_TAIL = 'echo "$reward" > /logs/verifier/reward.txt 2>/dev/null || true\necho "reward=$reward"\nexit 0\n'


def render_verifier(spec: TaskSpec) -> Tuple[str, Dict[str, str]]:
    v = spec.verifier
    if v.kind == "pytest_pr":
        return _render_pytest(spec), {}
    if v.kind == "module_check":
        extra = {}
        grader = "grade.py"
        if v.grader_script and Path(v.grader_script).exists():
            extra[grader] = Path(v.grader_script).read_text()
        return _render_module(spec), extra
    if v.kind == "readback":
        return _render_readback(spec), {}
    raise ValueError(f"unknown verifier kind {v.kind!r}")


def _render_pytest(spec: TaskSpec) -> str:
    root = spec.anchor.workdir + "/" + spec.anchor.backend_subdir if spec.anchor else "/app"
    f2p = " ".join(spec.verifier.f2p)
    p2p = " ".join(spec.verifier.p2p)
    return _HEAD + f'''# F2P (fail on the bug, pass on the fix) + P2P (regression guard), run in the SUT venv.
ROOT="${{ODDISH_ROOT:-{root}}}"
PY="$ROOT/.venv/bin/python"; [ -x "$PY" ] || PY=python3
cd "$ROOT" 2>/dev/null || true
F2P="{f2p}"
P2P="{p2p}"
"$PY" -m pytest -q $F2P $P2P > /logs/verifier/pytest.log 2>&1
rc=$?
tail -n 4 /logs/verifier/pytest.log 2>/dev/null || true
reward=0; [ "$rc" = 0 ] && reward=1
''' + _TAIL


def _render_module(spec: TaskSpec) -> str:
    root = spec.anchor.workdir + "/" + spec.anchor.backend_subdir if spec.anchor else "/app"
    return _HEAD + f'''# bespoke smoke grader (prints reward=0/1), run in the SUT venv.
ROOT="${{ODDISH_ROOT:-{root}}}"
PY="$ROOT/.venv/bin/python"; [ -x "$PY" ] || PY=python3
export PYTHONPATH="$ROOT:${{PYTHONPATH:-}}"
cd "$ROOT" 2>/dev/null || true
out="$("$PY" "$HERE/grade.py" 2>&1)"; echo "$out"
reward=0; echo "$out" | grep -q '^reward=1' && reward=1
''' + _TAIL


def _render_readback(spec: TaskSpec) -> str:
    """Integration: run each check's CLI through the agent's tools and assert on the output."""
    lines = [_HEAD, "# read final state back THROUGH the clone CLIs (never trust narration).", "ok=1"]
    for i, c in enumerate(spec.verifier.checks):
        cmd = c["cmd"].replace('"', '\\"')
        lines.append(f'out{i}="$({c["cmd"]} 2>/dev/null || true)"')
        if c.get("expect_substr"):
            sub = c["expect_substr"].replace('"', '\\"')
            lines.append(f'echo "$out{i}" | grep -qi "{sub}" || {{ echo "[verify] check {i} failed: missing {sub}"; ok=0; }}')
        elif c.get("py"):
            # python predicate over the variable `out` (stdout string); must print nothing / truthy return via exit code
            pred = c["py"].replace('"', '\\"')
            lines.append(f'python3 -c "import sys; out=sys.stdin.read(); sys.exit(0 if ({pred}) else 1)" <<< "$out{i}" '
                         f'|| {{ echo "[verify] check {i} predicate failed"; ok=0; }}')
    lines.append('reward=$ok')
    return "\n".join(lines) + "\n" + _TAIL


# --------------------------------------------------------------- build-time F2P/P2P derivation
def derive_pr_verifier(repo_dir: str, base_sha: str, head_sha: str,
                       test_cmd: str = "python -m pytest -q", changed_tests: List[str] = None) -> Dict[str, List[str]]:
    """Empirically find the fail-to-pass set: tests that FAIL at base_sha and PASS at head_sha.
    Runs the suite (or just the PR's changed test files, if given) at both commits. Returns
    {f2p, p2p, broken_at_base}. This is the pr_to_task move — derive the grader from the real fix.

    NOTE: mutates the working tree (checks out base then head); run on a throwaway clone."""
    repo = Path(repo_dir)

    import os
    def run_at(sha: str) -> Dict[str, str]:
        subprocess.run(["git", "-C", str(repo), "checkout", "-q", sha], check=True)
        # drop stale bytecode: git checkout sets mtimes to "now", and Python's 1s-resolution
        # .pyc invalidation can otherwise import the OTHER commit's code, corrupting F2P.
        for pc in repo.rglob("__pycache__"):
            shutil.rmtree(pc, ignore_errors=True)
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        target = " ".join(changed_tests) if changed_tests else ""
        p = subprocess.run(f"{test_cmd} {target} -rA --tb=no -q -p no:cacheprovider", cwd=str(repo),
                           shell=True, capture_output=True, text=True, timeout=1800, env=env)
        # parse pytest -rA "PASSED test::id" / "FAILED test::id"
        res = {}
        for ln in (p.stdout + p.stderr).splitlines():
            parts = ln.split()
            if len(parts) >= 2 and parts[0] in ("PASSED", "FAILED", "ERROR"):
                res[parts[1]] = parts[0]      # parts[1] = node id (FAILED <id> - <reason>)
        return res

    base = run_at(base_sha)
    head = run_at(head_sha)
    f2p = sorted(t for t, s in head.items() if s == "PASSED" and base.get(t) in ("FAILED", "ERROR", None))
    # only count as f2p if it actually existed & failed at base (a brand-new test that didn't exist
    # at base also qualifies — it's the PR's new coverage of the fix)
    f2p = sorted(t for t in f2p if base.get(t) != "PASSED")
    p2p = sorted(t for t, s in head.items() if s == "PASSED" and base.get(t) == "PASSED")
    return {"f2p": f2p, "p2p": p2p, "n_f2p": len(f2p), "n_p2p": len(p2p)}

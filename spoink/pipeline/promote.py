"""Promote gate — the empirical nop=0 / oracle=1 proof, in docker.

`validate.py` checks a task is well-formed (contract, no leakage, verifier tied to the fix).
`promote.py` proves the CODE CONTRACT actually holds: the fix's tests must FAIL on the shipped SUT
(nop) and PASS after applying the oracle patch (oracle). If both hold, the task is `proven` — it
will reward a real fix and punish doing nothing.

Runs in one throwaway container (the code fix is what nop/oracle grades; sidecar retrieval is a
separate concern covered by the validation gates). Reads the `.promote.json` manifest generate.py
emits. Best-effort dep install (uv sync / pip install) — a SUT that can't build reports `errored`,
which is honest signal about which candidates yield runnable tasks.
"""
from __future__ import annotations

import hashlib
import json
import shlex
import subprocess
from pathlib import Path
from typing import Any, Dict, List

RUNNER = r"""
set -e
cd /work
git clone --quiet "$BUNDLE" repo 2>/dev/null || git clone --quiet --mirror "$BUNDLE" repo.git
if [ -d repo.git ]; then git clone --quiet repo.git repo; fi
cd repo && git checkout --quiet "$BASE" 2>/dev/null || true
[ -n "$SUBDIR" ] && cd "$SUBDIR" || true
pip -q install pytest 2>/dev/null || true          # the harness always needs a test runner
# best-effort SUT deps
if [ -f uv.lock ] || grep -q '\[project\]' pyproject.toml 2>/dev/null; then
  pip -q install uv 2>/dev/null && uv sync --quiet 2>/dev/null || pip -q install -e . 2>/dev/null || true
elif [ -f requirements.txt ]; then pip -q install -r requirements.txt 2>/dev/null || true
elif [ -f pyproject.toml ] || [ -f setup.py ]; then pip -q install -e . 2>/dev/null || true
fi
run_tests() { python -m pytest $F2P -q -p no:cacheprovider >/tmp/out 2>&1; echo $?; }
NOP=$(run_tests)                                  # expect NON-zero (fail on the bug)
git apply --whitespace=nowarn /work/fix.patch 2>/dev/null || patch -p1 < /work/fix.patch 2>/dev/null || echo "PATCH_FAIL"
ORACLE=$(run_tests)                               # expect zero (pass after the fix)
echo "SPOINK_RESULT nop_exit=$NOP oracle_exit=$ORACLE"
"""


def _dc(project: str, compose: Path, *args: str, cwd: str, timeout: int = 1800):
    return subprocess.run(["docker", "compose", "-p", project, "-f", str(compose), *args],
                          cwd=cwd, capture_output=True, text=True, timeout=timeout)


def promote_compose(task_dir: str, *, timeout: int = 2400) -> Dict[str, Any]:
    """FULL-compose nop/oracle: build the per-repo SUT env + boot the evidence sidecars healthy,
    run the verifier with no change (nop -> expect 0), apply the oracle, run it again (oracle ->
    expect 1). Requires the sidecar gateway images to be real (published), not placeholders."""
    root = Path(task_dir)
    env = root / "environment"
    compose = next((env / f for f in ("docker-compose.yaml", "docker-compose.yml") if (env / f).exists()), None)
    if not compose:
        return {"status": "errored", "detail": "no docker-compose in environment/"}
    if "TODO" in compose.read_text():
        return {"status": "skipped", "detail": "sidecar images not published (placeholder tags) — publish first"}
    proj = "spoinkp" + hashlib.sha1(str(root).encode()).hexdigest()[:10]
    ecwd = str(env)

    def dc(*a, t=timeout):
        return _dc(proj, compose, *a, cwd=ecwd, timeout=t)

    def reward():
        r = dc("exec", "-T", "main", "cat", "/logs/verifier/reward.txt", t=60)
        return (r.stdout or "").strip()

    try:
        b = dc("build")
        if b.returncode != 0:
            return {"status": "errored", "mode": "compose", "detail": "compose build failed",
                    "log": (b.stderr or b.stdout)[-1200:]}
        u = dc("up", "-d", "--wait", "--wait-timeout", "180")
        if u.returncode != 0:
            return {"status": "errored", "mode": "compose", "detail": "sidecars didn't come up healthy",
                    "log": (u.stderr or u.stdout)[-1200:]}
        dc("cp", str(root / "tests"), "main:/htests", t=120)
        dc("cp", str(root / "solution"), "main:/hsol", t=120)
        dc("exec", "-T", "main", "mkdir", "-p", "/logs/verifier", t=60)
        dc("exec", "-T", "main", "bash", "/htests/test.sh", t=900)
        nop = reward()
        dc("exec", "-T", "main", "bash", "/hsol/solve.sh", t=900)
        dc("exec", "-T", "main", "bash", "/htests/test.sh", t=900)
        oracle = reward()
        proven = nop in ("0", "") and oracle == "1"
        return {"status": "proven" if proven else "failed", "mode": "compose",
                "proven": proven, "nop_reward": nop or "0", "oracle_reward": oracle or "?",
                "detail": f"nop reward={nop or '0'} (want 0); oracle reward={oracle or '?'} (want 1)"}
    except subprocess.TimeoutExpired:
        return {"status": "errored", "mode": "compose", "detail": f"timed out after {timeout}s"}
    finally:
        dc("down", "-v", "--remove-orphans", t=180)


def promote(task_dir: str, *, python_image: str = "python:3.11-slim", timeout: int = 1800) -> Dict[str, Any]:
    root = Path(task_dir)
    # prefer the FULL compose gate when the sidecar images are real (published)
    env = root / "environment"
    compose = next((env / f for f in ("docker-compose.yaml", "docker-compose.yml") if (env / f).exists()), None)
    if compose and "TODO" not in compose.read_text() and (root / "solution" / "solve.sh").exists():
        return promote_compose(task_dir, timeout=max(timeout, 2400))
    # else fall back to the single-container SUT code-contract proof
    man_p = root / ".promote.json"
    bundle = root / "environment" / "codebase.bundle"
    patch = root / "solution" / "fix.patch"
    if not man_p.exists() or not bundle.exists():
        return {"status": "errored", "detail": "task missing .promote.json or codebase.bundle"}
    man = json.loads(man_p.read_text())
    if man.get("verifier") != "pytest_pr" or not man.get("f2p"):
        return {"status": "skipped",
                "detail": f"promote runs pytest_pr tasks with a test target (got {man.get('verifier')}, "
                          f"{len(man.get('f2p') or [])} tests)"}
    if not patch.exists():
        return {"status": "errored", "detail": "no solution/fix.patch (no oracle to apply)"}

    f2p = " ".join(shlex.quote(t) for t in man["f2p"])
    env = ["-e", f"BASE={man.get('base_commit','')}", "-e", f"SUBDIR={man.get('backend_subdir','')}",
           "-e", f"F2P={f2p}", "-e", "BUNDLE=/work/codebase.bundle"]
    # git is needed inside the container
    script = "apt-get update -qq >/dev/null 2>&1 && apt-get install -y -qq git >/dev/null 2>&1; " + RUNNER
    # promote is a build/test step (not the agent) — it needs network to install git + deps
    cmd = ["docker", "run", "--rm",
           "-v", f"{bundle.resolve()}:/work/codebase.bundle:ro",
           "-v", f"{patch.resolve()}:/work/fix.patch:ro",
           *env, python_image, "bash", "-c", script]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"status": "errored", "detail": f"timed out after {timeout}s"}
    out = p.stdout + p.stderr
    marker = next((ln for ln in out.splitlines() if ln.startswith("SPOINK_RESULT")), "")
    if not marker:
        return {"status": "errored", "detail": "no result marker (SUT likely failed to build)",
                "log": out[-1200:]}
    kv = dict(tok.split("=", 1) for tok in marker.split()[1:])
    nop_exit, oracle_exit = kv.get("nop_exit", "?"), kv.get("oracle_exit", "?")
    nop_fails = nop_exit not in ("0", "?")
    oracle_passes = oracle_exit == "0"
    proven = nop_fails and oracle_passes
    return {"status": "proven" if proven else "failed",
            "proven": proven, "nop_exit": nop_exit, "oracle_exit": oracle_exit,
            "detail": (f"nop tests {'fail ✓' if nop_fails else 'PASS ✗ (bug not reproduced)'}; "
                       f"oracle tests {'pass ✓' if oracle_passes else 'FAIL ✗ (fix did not resolve)'}"),
            "log": out[-1200:]}

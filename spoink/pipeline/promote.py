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
git clone --quiet "$BUNDLE" repo 2>/dev/null || { git clone --quiet --mirror "$BUNDLE" repo.git && git clone --quiet repo.git repo; }
REPO=/work/repo
git -C "$REPO" checkout --quiet "$BASE" 2>/dev/null || true
WORK="$REPO"; [ -n "$SUBDIR" ] && WORK="$REPO/$SUBDIR"
cd "$WORK"
# build the SUT INTO A VENV (uv), so tests run against its real deps — not system python
PY=python3
if [ -f uv.lock ] || grep -q '\[project\]' pyproject.toml 2>/dev/null; then
  pip -q install uv >/dev/null 2>&1 || true
  # --all-extras/--all-groups pulls optional + dev deps (monorepos hide test deps like sqlalchemy there)
  uv sync --all-extras --all-groups >/tmp/build 2>&1 || uv sync >/tmp/build 2>&1 || uv sync --no-dev >/tmp/build 2>&1 || true
  [ -x "$WORK/.venv/bin/python" ] && PY="$WORK/.venv/bin/python"
elif [ -f requirements.txt ]; then pip -q install -r requirements.txt >/tmp/build 2>&1 || true
elif [ -f pyproject.toml ] || [ -f setup.py ]; then pip -q install -e . >/tmp/build 2>&1 || true
fi
"$PY" -m pip install -q pytest >/dev/null 2>&1 || true    # ensure a runner in the venv
run_tests() { "$PY" -m pytest $F2P -q -p no:cacheprovider >/tmp/out 2>&1; echo $?; }
# the PR often ADDS the failing test, so we can't run it at base directly. Instead:
#  oracle = full patch (fix + new tests) applied -> tests PASS;
#  nop    = same tree but the FIX files reverted to base -> the new tests FAIL (bug present).
# patch is repo-relative -> apply from the repo root, not the build subdir.
git -C "$REPO" apply --whitespace=nowarn /work/fix.patch 2>/tmp/patch || \
  ( cd "$REPO" && patch -p1 < /work/fix.patch >/tmp/patch 2>&1 ) || echo "PATCH_FAIL"
ORACLE=$(run_tests)                               # expect zero (pass with the fix)
if [ -n "$FIX_FILES" ]; then git -C "$REPO" checkout "$BASE" -- $FIX_FILES 2>/tmp/revert || true; fi
NOP=$(run_tests)                                  # expect NON-zero (fail once the fix is reverted)
echo "SPOINK_RESULT nop_exit=$NOP oracle_exit=$ORACLE"
echo "----- pytest (post-fix) tail -----"; tail -n 25 /tmp/out 2>/dev/null || true
echo "----- build tail -----"; tail -n 8 /tmp/build 2>/dev/null || true
echo "----- patch tail -----"; tail -n 5 /tmp/patch 2>/dev/null || true
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


def promote(task_dir: str, *, python_image: str = "python:3.13-slim", timeout: int = 1800) -> Dict[str, Any]:
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
    fix_files = " ".join(shlex.quote(f) for f in man.get("fix_files", []))
    env = ["-e", f"BASE={man.get('base_commit','')}", "-e", f"SUBDIR={man.get('backend_subdir','')}",
           "-e", f"F2P={f2p}", "-e", f"FIX_FILES={fix_files}", "-e", "BUNDLE=/work/codebase.bundle",
           "-e", "UV_CACHE_DIR=/root/.cache/uv", "-e", "PIP_CACHE_DIR=/root/.cache/pip"]
    # cache keyed BY REPO: same-repo candidates share the warm wheel cache (throughput), while
    # different repos are isolated so parallel promotes don't race on one cache (determinism).
    repo_slug = re.sub(r"[^a-z0-9]+", "-", (man.get("source_repo") or "shared").lower()).strip("-")
    cache = Path.home() / ".cache" / "spoink-promote" / repo_slug
    (cache / "uv").mkdir(parents=True, exist_ok=True); (cache / "pip").mkdir(parents=True, exist_ok=True)
    script = "apt-get update -qq >/dev/null 2>&1 && apt-get install -y -qq git >/dev/null 2>&1; " + RUNNER
    cmd = ["docker", "run", "--rm",
           "-v", f"{bundle.resolve()}:/work/codebase.bundle:ro",
           "-v", f"{patch.resolve()}:/work/fix.patch:ro",
           "-v", f"{cache / 'uv'}:/root/.cache/uv", "-v", f"{cache / 'pip'}:/root/.cache/pip",
           *env, python_image, "bash", "-c", script]

    def _attempt() -> Dict[str, Any]:
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return {"status": "errored", "detail": f"timed out after {timeout}s"}
        out = p.stdout + p.stderr
        marker = next((ln for ln in out.splitlines() if ln.startswith("SPOINK_RESULT")), "")
        if not marker:
            return {"status": "errored", "detail": "no result marker (SUT likely failed to build)", "log": out[-1200:]}
        kv = dict(tok.split("=", 1) for tok in marker.split()[1:])
        nop_exit, oracle_exit = kv.get("nop_exit", "?"), kv.get("oracle_exit", "?")
        nop_fails, oracle_passes = nop_exit not in ("0", "?"), oracle_exit == "0"
        proven = nop_fails and oracle_passes
        return {"status": "proven" if proven else "failed", "proven": proven,
                "nop_exit": nop_exit, "oracle_exit": oracle_exit,
                "detail": (f"nop tests {'fail ✓' if nop_fails else 'PASS ✗ (bug not reproduced)'}; "
                           f"oracle tests {'pass ✓' if oracle_passes else 'FAIL ✗ (fix did not resolve)'}"),
                "log": out[-1200:]}

    # retry once on a non-proven result — a build/network/flaky-test blip shouldn't sink a real task;
    # a task that flips across attempts is FLAKY (not trustworthy) and is flagged as such.
    r1 = _attempt()
    if r1.get("proven"):
        return r1
    r2 = _attempt()
    if r2.get("proven"):
        r2["flaky"] = True
        r2["detail"] = "PROVEN on retry (attempt 1 was non-proven) — FLAKY, not trustworthy: " + r2["detail"]
        return r2
    return r2 if r2.get("status") != "errored" else r1

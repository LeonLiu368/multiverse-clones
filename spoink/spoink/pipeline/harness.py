"""SUT build/test harness — the reproducibility layer.

Verifying a code task at scale needs the SUT to actually build and run its tests. This probes a
shipped `codebase.bundle` at the incident tip: clone it, detect the build system, confirm the fix's
test target exists, and (optionally) attempt the build. It's the honest signal about which mined
incidents yield *runnable* tasks — the 80% that decides whether a task is farmable.

Light mode (default) is fast + headless (git + file checks). Full mode attempts the dependency
install; the docker nop/oracle proof lives in promote.py (this shares the same reproducibility idea).
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional


def _run(args: List[str], cwd: Optional[str] = None, timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)


def _detect_build(repo: Path) -> str:
    if (repo / "uv.lock").exists():
        return "uv"
    if (repo / "pyproject.toml").exists():
        return "pip-e"
    if (repo / "requirements.txt").exists():
        return "pip-req"
    if (repo / "setup.py").exists():
        return "pip-e"
    if (repo / "package.json").exists():
        return "npm"
    return "unknown"


def probe_sut(bundle: str, base_sha: str = "", changed_tests: Optional[List[str]] = None,
              *, subdir: str = "", build: bool = False, timeout: int = 600) -> Dict[str, Any]:
    """Clone the (sliced) SUT bundle at the incident tip and report reproducibility signal.
    build=False -> structural only (build system + test-target existence). build=True -> also install."""
    changed_tests = changed_tests or []
    out: Dict[str, Any] = {"ok": False, "build_system": None, "has_test_target": False,
                           "built": None, "detail": ""}
    if not bundle or not Path(bundle).exists():
        out["detail"] = "no SUT bundle"
        return out
    tmp = tempfile.mkdtemp(prefix="spoink-harness-")
    try:
        cl = _run(["git", "clone", "--quiet", str(bundle), tmp], timeout=timeout)
        if cl.returncode != 0:
            out["detail"] = f"clone failed: {cl.stderr[-160:]}"; return out
        if base_sha:
            _run(["git", "-C", tmp, "checkout", "--quiet", base_sha], timeout=60)
        root = Path(tmp) / subdir if subdir else Path(tmp)
        bs = _detect_build(root)
        out["build_system"] = bs
        out["has_test_target"] = all((Path(tmp) / t).exists() for t in changed_tests) if changed_tests else None
        if build and bs in ("uv", "pip-e", "pip-req"):
            cmd = {"uv": ["bash", "-lc", "pip -q install uv && uv sync"],
                   "pip-e": ["pip", "-q", "install", "-e", "."],
                   "pip-req": ["pip", "-q", "install", "-r", "requirements.txt"]}[bs]
            b = _run(cmd, cwd=str(root), timeout=timeout)
            out["built"] = b.returncode == 0
            if b.returncode != 0:
                out["detail"] = f"build failed: {(b.stderr or b.stdout)[-200:]}"
        # "ok" = we have a recognizable build system and (if we tried) it built
        out["ok"] = bs != "unknown" and (out["built"] in (None, True))
        if out["ok"] and not out["detail"]:
            out["detail"] = f"{bs} project" + (" (built)" if out["built"] else "")
        return out
    except subprocess.TimeoutExpired:
        out["detail"] = f"timed out after {timeout}s"; return out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

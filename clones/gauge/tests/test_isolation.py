"""R6.3 isolation tests — run by DEFAULT (no docker, no GAUGE_RUN_DOCKER_SMOKE gate).

The thin agent image must carry the CLI/MCP tools but NOT the gateway's seed/state/query
source, so an agent can neither read the answer off disk nor `import` the generator and
recompute the world (the R2.k leak rule: grep is necessary but not sufficient). The agent
Dockerfiles strip `gauge/server/*` down to `__init__.py` + the pure `links.py` helper.

Here we reproduce that strip in a tmp tree (exactly the Dockerfile's `find ... -delete`)
and assert, in a clean subprocess:
  * `import gauge.server.state`  raises ModuleNotFoundError (seed/state loader gone),
  * `import gauge.server.query_engine` / `.app` / `.clone_admin` raise (no api/ surface),
  * no server source survives except __init__.py + links.py,
  * `gauge.cli.gcx` + `gauge.cli.mcp_server` STILL import (tools intact).

We also assert the agent Dockerfiles actually perform this strip + leak smoke test, so the
shipped images can't silently regress.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[1]
PKG = REPO / "gauge"
SERVER = PKG / "server"

# Modules that MUST disappear from the agent (seed/state/query/api/admin surface).
LEAK_MODULES = [
    "gauge.server.state",
    "gauge.server.query_engine",
    "gauge.server.app",
    "gauge.server.clone_admin",
    "gauge.server.dashboards",
    "gauge.server.alerts",
    "gauge.server.datasources",
    "gauge.server.annotations",
    "gauge.server.auth",
]


def _strip_agent_tree(dest: Path) -> Path:
    """Mirror the agent Dockerfile: copy the package, then remove every server module
    except __init__.py and the pure links.py helper."""
    pkg_root = dest / "gauge"
    shutil.copytree(PKG, pkg_root)
    for py in (pkg_root / "server").glob("*.py"):
        if py.name not in ("__init__.py", "links.py"):
            py.unlink()
    for cache in pkg_root.rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)
    return dest


def _run_py(pythonpath: Path, code: str) -> subprocess.CompletedProcess[str]:
    # Resolve `gauge` ONLY from the stripped tree, exactly like the agent image's sys.path:
    #   * `-S` skips site processing so an editable `gauge` install (a .pth finder in
    #     site-packages) can't shadow it,
    #   * `cwd=pythonpath` so the implicit sys.path[0]="" entry points at the stripped tree
    #     (not the repo source), and PYTHONPATH reinforces it.
    return subprocess.run(
        [sys.executable, "-S", "-c", code],
        env={"PYTHONPATH": str(pythonpath), "PATH": "/usr/bin:/bin"},
        cwd=str(pythonpath),
        text=True,
        capture_output=True,
        timeout=30,
    )


@pytest.fixture(scope="module")
def stripped_tree(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _strip_agent_tree(tmp_path_factory.mktemp("agent"))


@pytest.mark.parametrize("module", LEAK_MODULES)
def test_server_module_not_importable_in_agent(stripped_tree: Path, module: str) -> None:
    result = _run_py(stripped_tree, f"import {module}")
    assert result.returncode != 0, f"{module} should NOT import in the stripped agent tree"
    assert "ModuleNotFoundError" in result.stderr, result.stderr


def test_no_server_source_survives_strip(stripped_tree: Path) -> None:
    survivors = sorted(p.name for p in (stripped_tree / "gauge" / "server").glob("*.py"))
    assert survivors == ["__init__.py", "links.py"], survivors


def test_tools_still_import_after_strip(stripped_tree: Path) -> None:
    result = _run_py(stripped_tree, "import gauge.cli.gcx, gauge.cli.mcp_server; print('ok')")
    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout


def test_links_helper_pure_after_strip(stripped_tree: Path) -> None:
    # links.py is the only server module the tools import; it must work standalone.
    code = (
        "from gauge.server import links; "
        "print(links.dashboard_link('http://gauge', {'uid': 'd1', 'title': 'X'})['path'])"
    )
    result = _run_py(stripped_tree, code)
    assert result.returncode == 0, result.stderr
    assert "/d/d1/" in result.stdout


def test_agent_dockerfiles_strip_and_probe() -> None:
    """The shipped agent Dockerfiles must perform the strip AND the import-leak smoke test."""
    dockerfiles = [
        REPO / "examples" / "task-pack-compose" / "Dockerfile.agent",
        REPO / "oddish" / "tasks" / "gauge-annotation-roundtrip" / "environment" / "Dockerfile",
    ]
    for df in dockerfiles:
        text = df.read_text()
        assert "gauge/server" in text and "-delete" in text, f"{df} does not strip server source"
        assert "import gauge.server.state" in text, f"{df} lacks the import-leak smoke probe"
        assert "links.py" in text, f"{df} must preserve links.py"

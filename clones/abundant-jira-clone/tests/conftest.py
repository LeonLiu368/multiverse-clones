"""Shared fixtures for the jira-clone test suite.

Boots a `jira-gateway:empty` sidecar with the small deterministic WEB fixture mounted
(the same `tasks/jira-assignee-count/environment/data/state.json`), then points both the
`jira`/`linear` CLI (remote mode) and the `mcp/` MCP tools at it over HTTP. Writes are
exercised against this throwaway gateway, so the shared prod corpus is never touched and
each session starts from the same baked fixture (determinism).

The suite runs anywhere Docker is available:
  - locally:  `pytest tests/`  (build the images first via selfcontained/base/build.sh)
  - in CI:    same, after the build job tags `jira-gateway:empty`
If an external gateway is already running, set `JIRA_TEST_BASE_URL` to skip the container
boot (read-only tests only — write tests will mutate that gateway).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_STATE = REPO_ROOT / "tasks" / "jira-assignee-count" / "environment" / "data" / "state.json"
GATEWAY_IMAGE = os.environ.get("JIRA_GATEWAY_IMAGE", "jira-gateway:empty")
MCP_PKG_PARENT = str(REPO_ROOT)  # so `import mcp.server` resolves
TICKETVECTOR_IMAGE = os.environ.get(
    "TICKETVECTOR_IMAGE", "ghcr.io/abundant-ai/ticketvector-service:latest"
)


def _ensure_world_issues_on_path() -> None:
    """Make the upstream `world_issues` CLI package importable for the parity tests.

    The CLI lives in the ticketvector image, not this repo (the agent build strips it down,
    R2.k). For host-side parity tests we extract a *clean* copy of the package from the
    service image into a temp dir and put it on sys.path. This is test scaffolding only — it
    never ships in the agent. Best-effort: if docker/image is missing, parity tests skip."""
    try:
        import world_issues.cli  # noqa: F401
        return
    except Exception:
        pass
    if not shutil.which("docker"):
        return
    dest = Path(os.environ.get("PYTEST_TMP_WORLD_ISSUES", "/tmp/jira-clone-world-issues"))
    pkg = dest / "world_issues"
    if not (pkg / "cli.py").exists():
        dest.mkdir(parents=True, exist_ok=True)
        cid = subprocess.run(
            ["docker", "create", TICKETVECTOR_IMAGE], capture_output=True, text=True
        ).stdout.strip()
        if not cid:
            return
        try:
            subprocess.run(
                ["docker", "cp", f"{cid}:/opt/ticketvector/world_issues/.", str(pkg)],
                capture_output=True,
            )
        finally:
            subprocess.run(["docker", "rm", cid], capture_output=True)
    if str(dest) not in sys.path and (pkg / "cli.py").exists():
        sys.path.insert(0, str(dest))


_ensure_world_issues_on_path()


def _wait_health(base_url: str, timeout: float = 60.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(base_url + "/health", timeout=2) as resp:
                if resp.status == 200:
                    return
        except (urllib.error.URLError, ConnectionError, OSError):
            time.sleep(1)
    raise RuntimeError(f"gateway never became healthy at {base_url}")


@pytest.fixture(scope="session")
def base_url() -> str:
    """A live gateway base URL. Boots jira-gateway:empty + WEB fixture unless overridden."""
    external = os.environ.get("JIRA_TEST_BASE_URL")
    if external:
        _wait_health(external.rstrip("/"))
        yield external.rstrip("/")
        return

    if not FIXTURE_STATE.exists():
        pytest.skip(f"fixture state not found: {FIXTURE_STATE}")
    name = f"jira-test-gw-{uuid.uuid4().hex[:8]}"
    port = 18801
    proc = subprocess.run(
        [
            "docker", "run", "-d", "--name", name, "--platform", "linux/amd64",
            "-p", f"{port}:8765",
            "-v", f"{FIXTURE_STATE}:/var/lib/ticketvector/state.json:ro",
            # The gateway stamps comment authorship from its own actor; use a real WEB user
            # so add_comment / assignee=me resolve (the agent in a real task is a known user).
            "-e", "WORLD_ISSUES_ACTOR=priya.singh",
            GATEWAY_IMAGE,
        ],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        pytest.skip(f"could not start gateway image {GATEWAY_IMAGE}: {proc.stderr.strip()}")
    url = f"http://127.0.0.1:{port}"
    try:
        _wait_health(url)
        yield url
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)


@pytest.fixture(scope="session")
def cli_env(base_url: str) -> dict[str, str]:
    """Environment that makes the real `world_issues.cli` dispatch in remote mode.

    The CLI reads these via `load_config()`; we set them on os.environ for the in-process
    `run(...)` calls in `cli()` below."""
    env = {
        "WORLD_ISSUES_BACKEND": "remote",
        "WORLD_ISSUES_AGENT_MODE": "1",
        "WORLD_ISSUES_OUTPUT": "json",
        "WORLD_ISSUES_ACTOR": "agent",
        "WORLD_ISSUES_DEFAULT_PROJECT": "WEB",
        "PLANE_BASE_URL": base_url,
    }
    os.environ.update(env)
    return env


@pytest.fixture(scope="session")
def mcp_server(base_url: str, cli_env: dict[str, str]):
    """Import the MCP server module with PLANE_BASE_URL pointed at the gateway."""
    os.environ["PLANE_BASE_URL"] = base_url
    if MCP_PKG_PARENT not in sys.path:
        sys.path.insert(0, MCP_PKG_PARENT)
    from mcp import server  # import here so PLANE_BASE_URL is set first
    return server


def has_cli() -> bool:
    """True if the upstream `world_issues.cli` is importable (i.e. tests run where the
    gateway package is on PYTHONPATH). When False, CLI/parity tests skip; MCP-vs-/rpc
    tests still run."""
    try:
        if MCP_PKG_PARENT not in sys.path:
            sys.path.insert(0, MCP_PKG_PARENT)
        import world_issues.cli  # noqa: F401
        return True
    except Exception:
        return False


def cli(program: str, *args: str) -> dict | list:
    """Invoke the REAL CLI dispatch in-process: `world_issues.cli.run(program, args)`.

    `run` is the exact entrypoint `jira`/`linear`/`world-issues` console scripts call
    (program = argv[0] basename). On success the result is emitted on stdout as JSON; on
    error the JSON error envelope is emitted on stderr and a non-zero code returned. We
    capture both and raise CliError (carrying the envelope text) on failure."""
    import contextlib
    import io

    from world_issues.cli import run

    out_buf, err_buf = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
        code = run(program, list(args))
    out = out_buf.getvalue().strip()
    err = err_buf.getvalue().strip()
    if code != 0:
        raise CliError(code, err or out)
    return json.loads(out) if out else {}


class CliError(RuntimeError):
    def __init__(self, code: int, output: str) -> None:
        super().__init__(f"CLI exited {code}: {output}")
        self.code = code
        self.output = output

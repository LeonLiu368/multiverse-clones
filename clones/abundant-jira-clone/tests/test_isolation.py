"""R6.3 / R2.k — agent isolation.

Asserts, inside the built `jira-agent` image, that:
  1. there is NO seed/state data on disk (the agent can only reach state over HTTP);
  2. the gateway's seed GENERATOR is not importable (`import world_issues.seed` raises) —
     grep-for-the-answer is insufficient when the answer is recomputable;
  3. no `seed`/`server`/`api` source survives in the agent;
  4. the CLI + MCP tool surface IS present and importable (the agent keeps its tools).

These run `docker run` against `jira-agent:latest`; skipped if the image isn't built or
Docker is unavailable. Build it first: `selfcontained/base/build.sh`.
"""

from __future__ import annotations

import shutil
import subprocess

import pytest

AGENT_IMAGE = "jira-agent:latest"


def _docker_available() -> bool:
    return shutil.which("docker") is not None


def _image_exists(image: str) -> bool:
    proc = subprocess.run(["docker", "image", "inspect", image], capture_output=True)
    return proc.returncode == 0


pytestmark = pytest.mark.skipif(
    not (_docker_available() and _image_exists(AGENT_IMAGE)),
    reason=f"{AGENT_IMAGE} not built or docker unavailable",
)


def _run(cmd: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", "run", "--rm", "--platform", "linux/amd64", "--entrypoint", "sh", AGENT_IMAGE, "-c", cmd],
        capture_output=True, text=True,
    )


def test_no_state_json_on_disk():
    proc = _run("test -e /var/lib/ticketvector/state.json && echo PRESENT || echo SEALED")
    assert "SEALED" in proc.stdout
    assert "PRESENT" not in proc.stdout


def test_seed_generator_not_importable():
    proc = _run("python3 -c 'import world_issues.seed' 2>&1 || true")
    assert "ModuleNotFoundError" in proc.stdout + proc.stderr


@pytest.mark.parametrize("mod", ["server", "plane", "demo", "runtime", "snapshot"])
def test_gateway_modules_not_importable(mod):
    proc = _run(f"python3 -c 'import world_issues.{mod}' 2>&1 || true")
    assert "ModuleNotFoundError" in proc.stdout + proc.stderr


def test_no_seed_or_server_source_on_disk():
    proc = _run(
        "find /opt -path '*world_issues*' \\( -name 'seed.py' -o -name 'server.py' "
        "-o -name 'plane.py' -o -name 'demo.py' \\) 2>/dev/null; echo END"
    )
    # Only the END marker should print — no matching source files.
    assert proc.stdout.strip() == "END"


def test_cli_still_importable_and_present():
    proc = _run("python3 -c 'import world_issues.cli; print(\"OK\")' && command -v jira linear")
    assert "OK" in proc.stdout
    assert "/usr/local/bin/jira" in proc.stdout


def test_mcp_server_present_and_lists_tools():
    proc = _run(
        "JIRA_MCP_FORCE_FALLBACK=1 python3 -c \""
        "import sys; sys.path.insert(0,'/opt/jira-mcp'); from mcp import server; "
        "print(sorted(server.TOOL_NAMES))\""
    )
    assert "search_issues" in proc.stdout and "transition_issue" in proc.stdout

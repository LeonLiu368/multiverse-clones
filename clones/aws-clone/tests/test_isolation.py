"""In-agent isolation tests (R6.3 / leak rule R2.k).

Builds the thin agent image (``Dockerfile.tools``) and asserts that:
  1. no seed corpus / state.json is on disk,
  2. ``import aws_clone.seed`` raises ModuleNotFoundError (the generator is not
     importable — grep alone is insufficient when an answer is recomputable),
  3. no ``aws_clone/seed`` or ``aws_clone/admin`` source survives in the agent,
  4. the seeded corpus answer is not greppable on the image,
  5. the agent CAN still load its tools: the real CLI and the ``aws-mcp`` MCP
     server both import.

Gated on ``AWS_CLONE_RUN_DOCKER_SMOKE=1`` (Docker required), mirroring the other
docker smoke tests.
"""

from __future__ import annotations

import os
import shutil
import subprocess

import pytest

from tests.helpers import docker_available

SMOKE = os.environ.get("AWS_CLONE_RUN_DOCKER_SMOKE") == "1"
IMAGE = "aws-clone-tools:isolation"
pytestmark = pytest.mark.skipif(
    not SMOKE or not shutil.which("docker") or not docker_available(),
    reason="set AWS_CLONE_RUN_DOCKER_SMOKE=1 with Docker available",
)


@pytest.fixture(scope="module", autouse=True)
def _build_agent_image() -> None:
    subprocess.run(["docker", "build", "-f", "Dockerfile.tools", "-t", IMAGE, "."], check=True, timeout=600)


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", "run", "--rm", IMAGE, *cmd], text=True, capture_output=True, timeout=60)


def test_no_state_corpus_on_disk() -> None:
    out = _run(["sh", "-c", "find / -name 'state.json' 2>/dev/null; true"])
    assert "aws-clone" not in out.stdout, out.stdout


def test_seed_generator_not_importable() -> None:
    out = _run(["python", "-c", "import aws_clone.seed"])
    assert out.returncode != 0
    assert "ModuleNotFoundError" in out.stderr or "No module named" in out.stderr


def test_admin_server_not_importable() -> None:
    out = _run(["python", "-c", "import aws_clone.admin.app"])
    assert out.returncode != 0


def test_no_seed_or_admin_source() -> None:
    out = _run(["sh", "-c", "find /opt/aws-clone -path '*/seed/*' -o -path '*/admin/*'; true"])
    assert out.stdout.strip() == "", out.stdout


def test_answer_not_greppable() -> None:
    # corpus answers from the example/seed states must not be on the agent image.
    out = _run(["sh", "-c", "grep -rs 'acme-payment-exports' /opt /usr/local 2>/dev/null; echo done"])
    assert "acme-payment-exports" not in out.stdout, out.stdout


def test_tools_still_load() -> None:
    out = _run(["python", "-c", "import aws_clone.mcp.server, aws_clone.mcp.tools; print('ok')"])
    assert out.returncode == 0, out.stderr
    assert "ok" in out.stdout
    assert _run(["sh", "-c", "command -v aws && command -v awslocal && command -v aws-mcp"]).returncode == 0

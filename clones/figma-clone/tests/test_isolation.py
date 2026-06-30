"""R6.3 isolation / leak gate.

Two layers:

1. **Agent-image checks** (run inside the built ``main`` container, or any env where
   ``FIGMACLONE_AGENT_IMAGE=1``): the gateway's API + seed/generator source must be
   stripped, the planted answer must not be greppable, and no service state file may
   exist on the agent disk. This is the same contract docker/Dockerfile.agent and the
   task environment/Dockerfile enforce at build time; here it is an executable test so
   it also runs from a cold ``docker compose`` against the real image.

2. **Source-tree invariants** (always run): the agent reaches state only over HTTP
   (the CLI/MCP carry no embedded DB), and the agent Dockerfiles actually strip the
   gateway source — so a regression that re-ships ``seed/``/``api/`` to the agent fails
   the suite even without Docker.
"""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
ANSWER = "#1D4ED8"  # the planted CTA / Primary-500 color the spec-recovery task hides
AGENT_DOCKERFILES = [
    REPO / "docker" / "Dockerfile.agent",
    REPO / "oddish" / "tasks" / "figma-spec-recovery" / "environment" / "Dockerfile",
]


# --------------------------------------------------------------------------- layer 1
def _on_agent_image() -> bool:
    return os.environ.get("FIGMACLONE_AGENT_IMAGE") == "1"


agent_only = pytest.mark.skipif(
    not _on_agent_image(),
    reason="agent-image checks run inside the built main container (FIGMACLONE_AGENT_IMAGE=1)",
)


@agent_only
def test_seed_generator_not_importable():
    """The deterministic seed generator must not be importable on the agent."""
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("figmaclone.seed")


@agent_only
def test_api_server_not_importable():
    """The gateway HTTP API must not be importable on the agent."""
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("figmaclone.api.app")


@agent_only
def test_no_api_or_seed_source_on_disk():
    import figmaclone
    pkg = Path(figmaclone.__file__).parent
    assert not (pkg / "api").exists(), f"{pkg/'api'} survived on the agent"
    assert not (pkg / "seed").exists(), f"{pkg/'seed'} survived on the agent"


@agent_only
def test_answer_not_greppable():
    """The planted answer color must not appear anywhere on the agent install dirs."""
    roots = ["/opt", "/app", "/usr/local/lib", "/workspace"]
    roots = [r for r in roots if os.path.isdir(r)]
    hit = subprocess.run(["grep", "-rsl", ANSWER, *roots], capture_output=True, text=True)
    # exclude the candidate's own card.py if the agent has already written the answer
    leaks = [ln for ln in hit.stdout.splitlines() if "/workspace/" not in ln]
    assert not leaks, f"answer {ANSWER!r} greppable on agent at: {leaks}"


@agent_only
def test_no_service_state_on_disk():
    for p in ("/srv/figma.db", "/srv/fixture.json"):
        assert not os.path.exists(p), f"service state {p} present on the agent"


@agent_only
def test_tools_still_load_on_agent():
    importlib.import_module("figmaclone.cli.main")
    importlib.import_module("figmaclone.mcp.server")


# --------------------------------------------------------------------------- layer 2
# Source-tree invariants — only meaningful where the repo source is checked out
# (the dev venv / CI). Inside the stripped agent image there is no repo source, so
# these skip and the agent-image layer above is what guards the container.
source_tree = pytest.mark.skipif(
    not (REPO / "src" / "figmaclone" / "seed" / "generator.py").exists(),
    reason="repo source tree not present (running inside the stripped agent image)",
)


@source_tree
def test_cli_carries_no_embedded_db():
    """The CLI module reaches state only over HTTP — no bundled SQLite db."""
    import figmaclone.cli.main as cli
    src = Path(cli.__file__).read_text()
    assert "FIGMA_API_URL" in src and "httpx" in src
    # the CLI must not open a local figma.db for client reads
    assert ".db" not in src.replace("figma.db", "")  # only the seed --out default mentions a db


@source_tree
def test_agent_dockerfiles_strip_gateway_source():
    """Both agent Dockerfiles must rm the installed api/ and seed/ packages."""
    for df in AGENT_DOCKERFILES:
        text = df.read_text()
        assert "rm -rf" in text and '"$PKG/api"' in text and '"$PKG/seed"' in text, (
            f"{df} does not strip the gateway api/ + seed/ source from the agent"
        )


@source_tree
def test_agent_dockerfiles_assert_no_leak():
    """Both agent Dockerfiles build-time-assert the seed is gone + answer absent."""
    for df in AGENT_DOCKERFILES:
        text = df.read_text()
        assert "import figmaclone.seed" in text, f"{df} lacks a seed-import leak assertion"


@source_tree
def test_self_grep_finds_answer_in_seed():
    """Sanity: the answer DOES live in the gateway seed source (so the strip matters)."""
    gen = (REPO / "src" / "figmaclone" / "seed" / "generator.py").read_text()
    assert ANSWER in gen, "expected the planted answer in the seed generator (test fixture drift?)"

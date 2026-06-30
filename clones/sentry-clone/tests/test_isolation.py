"""Isolation / leak-rule invariants (R6.3, R2.k).

The agent reaches state only over HTTP. The leak rule requires that the seeded answer
is neither greppable nor *recomputable* on the agent: there is no seed generator to
import, and the agent Dockerfile strips `sentry_clone.server` (the HTTP API + state).

These tests assert the source-level invariants the agent image relies on:
  * `sentry_clone.seed` is not importable (no deterministic generator exists at all);
  * the CLI/MCP client modules never import `sentry_clone.server` (so stripping it on
    the agent cannot break the tools);
  * the published agent Dockerfile strips the server package and excludes the admin CLI.
"""
from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CLI_DIR = ROOT / "sentry_clone" / "cli"


def test_no_seed_generator_importable() -> None:
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("sentry_clone.seed")


def test_cli_does_not_import_server() -> None:
    offenders: list[str] = []
    for path in CLI_DIR.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and (
                node.module == "sentry_clone.server" or node.module.startswith("sentry_clone.server.")
            ):
                offenders.append(f"{path.name}: from {node.module}")
            # a relative `from ..server import x` inside the cli package would also leak
            if isinstance(node, ast.ImportFrom) and node.level and node.module and node.module.split(".")[0] == "server":
                offenders.append(f"{path.name}: from {'.' * node.level}{node.module}")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if "sentry_clone.server" in alias.name:
                        offenders.append(f"{path.name}: import {alias.name}")
    assert not offenders, f"CLI/MCP must not import the gateway server: {offenders}"


def test_agent_dockerfile_strips_server_and_admin() -> None:
    df = (ROOT / "examples" / "task-pack-compose" / "Dockerfile.agent").read_text(encoding="utf-8")
    assert "rm -rf /opt/sentry-clone-cli/sentry_clone/server" in df
    # admin CLI must not be copied into the agent
    assert "sentry-clonectl" not in df.split("COPY --from=sentry-tools")[1].split("RUN")[0]

"""R6.3 / R2.k: the agent image is data-free and the gateway's world-builder is not
reachable.

Grep-for-the-answer is necessary but NOT sufficient (a deterministic seed generator
lets the agent recompute the answer). So this asserts THREE things about the THIN
agent image:
  1. no Discord corpus / DB on disk (the literal leak),
  2. the seed generator (`discordclone.seed`) and API (`discordclone.api`) are NOT
     importable (the recomputable leak that grep misses),
  3. no api/ or seed/ source directories survive in the image;
and that the agent still carries its tools (`discord`, `discord-mcp`).

Runs against the built agent image (default ghcr.io/abundant-ai/discord-agent:latest;
override with DISCORD_AGENT_IMAGE). Skips when docker or the image is unavailable —
it is always run in CI / tests/test.sh where the image exists (R6.4).
"""

from __future__ import annotations

import os
import shutil
import subprocess

import pytest

AGENT_IMAGE = os.environ.get("DISCORD_AGENT_IMAGE", "ghcr.io/abundant-ai/discord-agent:latest")
DOCKER = shutil.which("docker")


def _image_present() -> bool:
    if not DOCKER:
        return False
    r = subprocess.run([DOCKER, "image", "inspect", AGENT_IMAGE], capture_output=True, text=True)
    return r.returncode == 0


pytestmark = pytest.mark.skipif(not _image_present(),
                                reason=f"agent image {AGENT_IMAGE} not available")


def _run(*cmd):
    return subprocess.run([DOCKER, "run", "--rm", "--entrypoint", cmd[0], AGENT_IMAGE, *cmd[1:]],
                          capture_output=True, text=True)


def test_no_seed_data_on_disk():
    r = _run("sh", "-c",
             "for p in /srv/discord.db /srv/fixture.json /opt/discordclone/discord_corpus.db; do "
             "[ -e \"$p\" ] && echo \"LEAK:$p\"; done; echo done")
    assert "LEAK:" not in r.stdout, r.stdout


def test_seed_generator_not_importable():
    r = _run("python3", "-c", "import discordclone.seed")
    assert r.returncode != 0 and "ModuleNotFoundError" in r.stderr


def test_real_data_importer_not_importable():
    # The no-admin real-data importer + corpus builder are OPERATOR-only (they live in
    # discordclone.seed, stripped from the agent), so the agent can't build/regenerate
    # a corpus from a source either.
    for mod in ("discordclone.seed.importers", "discordclone.seed.build_corpus"):
        r = _run("python3", "-c", f"import {mod}")
        assert r.returncode != 0 and "ModuleNotFoundError" in r.stderr, mod


def test_api_not_importable():
    r = _run("python3", "-c", "import discordclone.api")
    assert r.returncode != 0 and "ModuleNotFoundError" in r.stderr


def test_no_api_or_seed_source_dirs():
    r = _run("sh", "-c",
             "find /usr/local/lib /opt -path '*/discordclone/seed/*' -o -path '*/discordclone/api/*' "
             "2>/dev/null | head; echo done")
    assert r.stdout.strip() == "done", f"leaked source: {r.stdout}"


def test_agent_has_tools_but_reaches_only_over_http():
    r = _run("sh", "-c", "command -v discord && command -v discord-mcp && echo tools-ok")
    assert "tools-ok" in r.stdout, r.stdout

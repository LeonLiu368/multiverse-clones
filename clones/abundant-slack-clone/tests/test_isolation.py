"""R6.3 / R2.k: the agent image is data-free and the gateway's world-builder is not reachable.

Grep-for-the-answer is necessary but NOT sufficient (a deterministic seed generator lets the agent
recompute the answer). So this asserts THREE things about the THIN agent image:
  1. no Slack data / DB on disk (the literal leak),
  2. the importer/seed (`import_export`) and gateway store (`slackgw`) are NOT importable
     (the recomputable leak that grep misses),
  3. no gateway api/seed source directories survive in the image.

Runs against the built agent image (default ghcr.io/abundant-ai/slack-agent:slack-mcp-oss; override
with SLACK_AGENT_IMAGE). Skips when docker or the image is unavailable — it is always run in CI /
tests/test.sh where the image exists, which is where R6.4 is asserted.
"""
from __future__ import annotations

import os
import shutil
import subprocess

import pytest

AGENT_IMAGE = os.environ.get("SLACK_AGENT_IMAGE", "ghcr.io/abundant-ai/slack-agent:slack-mcp-oss")
DOCKER = shutil.which("docker")


def _image_present() -> bool:
    if not DOCKER:
        return False
    r = subprocess.run([DOCKER, "image", "inspect", AGENT_IMAGE],
                       capture_output=True, text=True)
    return r.returncode == 0


pytestmark = pytest.mark.skipif(not _image_present(),
                                reason=f"agent image {AGENT_IMAGE} not available")


def _run(*cmd):
    return subprocess.run([DOCKER, "run", "--rm", "--entrypoint", cmd[0], AGENT_IMAGE, *cmd[1:]],
                          capture_output=True, text=True)


def test_no_seed_data_on_disk():
    r = _run("sh", "-c",
             "for p in /data/slack-export /tmp/slack.db /opt/slackgw /opt/import_export.py "
             "/opt/slack.prebuilt.db; do [ -e \"$p\" ] && echo \"LEAK:$p\"; done; echo done")
    assert "LEAK:" not in r.stdout, r.stdout


def test_answer_not_greppable():
    # No baked corpus text anywhere the agent can read.
    r = _run("sh", "-c",
             "grep -rsl 'slack-export' /data /opt /app /usr/local 2>/dev/null | head; echo done")
    assert r.stdout.strip() == "done", f"unexpected matches: {r.stdout}"


def test_importer_not_importable():
    r = _run("python3", "-c", "import import_export")
    assert r.returncode != 0 and "ModuleNotFoundError" in r.stderr


def test_gateway_store_not_importable():
    r = _run("python3", "-c", "import slackgw.store")
    assert r.returncode != 0 and "ModuleNotFoundError" in r.stderr


def test_no_api_or_seed_source_dirs():
    r = _run("sh", "-c",
             "find /opt -path '*/seed/*' -o -path '*/api/*' -o -name 'import_export.py' "
             "2>/dev/null | head; echo done")
    assert r.stdout.strip() == "done", f"leaked source: {r.stdout}"


def test_agent_has_tools_but_reaches_only_over_http():
    # The agent CAN drive Slack — the tools are present — it just can't bypass the gateway.
    r = _run("sh", "-c", "command -v slack && command -v slack-mcp && echo tools-ok")
    assert "tools-ok" in r.stdout, r.stdout

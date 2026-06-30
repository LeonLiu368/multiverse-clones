"""R6.3 isolation / import-leak: the AGENT image must carry no corpus and no gateway
API/seed source — state is reachable only over HTTP. Skips if the agent image isn't
built locally (e.g. CI without the image)."""
import shutil
import subprocess

import pytest

AGENT = "ghcr.io/abundant-ai/logfire-agent:latest"


def _have_image():
    if not shutil.which("docker"):
        return False
    r = subprocess.run(["docker", "image", "inspect", AGENT],
                       capture_output=True)
    return r.returncode == 0


pytestmark = pytest.mark.skipif(not _have_image(), reason="agent image not built locally")


def _run(cmd):
    return subprocess.run(["docker", "run", "--rm", AGENT] + cmd, capture_output=True, text=True)


def test_no_corpus_on_agent():
    r = _run(["sh", "-c", "[ ! -e /data/records.json ] && [ ! -e /data/records.json.gz ] && echo SEALED || echo LEAK"])
    assert "SEALED" in r.stdout


def test_server_not_importable():
    r = _run(["python", "-c", "import logfire_clone.server"])
    assert r.returncode != 0 and "ModuleNotFoundError" in r.stderr


def test_no_server_source():
    r = _run(["sh", "-c", "[ ! -e /opt/logfire_clone/server.py ] && echo OK || echo LEAK"])
    assert "OK" in r.stdout


def test_answer_not_greppable():
    # the graded answer literal must not appear anywhere on the agent's code paths
    r = _run(["grep", "-rs", "locked_at", "/opt", "/usr/local"])
    assert r.stdout.strip() == ""

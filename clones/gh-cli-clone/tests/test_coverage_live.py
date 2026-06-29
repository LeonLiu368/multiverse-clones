"""Live exhaustive coverage: run every agent-facing command through the `gh`
shim against a running forge (scripts/agent-coverage.sh). Opt-in via GHC_HOST/TOKEN."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    not (os.getenv("GHC_HOST") and os.getenv("GHC_TOKEN")),
    reason="set GHC_HOST + GHC_TOKEN (forge up) to run exhaustive command coverage",
)


def test_every_agent_command_works():
    script = Path(__file__).resolve().parents[1] / "scripts" / "agent-coverage.sh"
    res = subprocess.run(["bash", str(script)], capture_output=True, text=True)
    # the harness prints a per-command table and exits non-zero on any failure
    assert res.returncode == 0, res.stdout + res.stderr
    assert "0 failed" in res.stdout

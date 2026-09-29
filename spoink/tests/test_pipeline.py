from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from spoink.pipeline import Anchor, Surface, TaskSpec, VerifierSpec, generate_task  # noqa: E402
from spoink.pipeline.verifier import derive_pr_verifier  # noqa: E402


def test_generate_observability(tmp_path):
    bundle = tmp_path / "codebase.bundle"; bundle.write_bytes(b"PACK")
    grader = tmp_path / "grade.py"; grader.write_text("print('reward=1')\n")
    spec = TaskSpec(
        name="demo/preview-500s", kind="observability", incident_t="2026-06-25T00:34:00Z",
        instruction="Hey, previews are 500ing — take a look in the infra channel.",
        surfaces=[
            Surface("logfire", str(tmp_path / "logfire.json"), "ghcr.io/abundant-ai/logfire-gateway:t"),
            Surface("slack", str(tmp_path / "slack-export"), "ghcr.io/abundant-ai/slack-gateway:t"),
            Surface("linear", str(tmp_path / "state.json"), "ghcr.io/abundant-ai/jira-gateway:t"),
        ],
        verifier=VerifierSpec(kind="module_check", grader_script=str(grader)),
        anchor=Anchor(bundle=str(bundle), commit="16595d173abc", backend_subdir="backend"),
        source_repo="abundant-ai/oddish", fixed_by_pr="468")
    out = generate_task(spec, str(tmp_path / "out"))
    root = Path(out["task_dir"])

    for rel in ("task.toml", "instruction.md", "environment/Dockerfile",
                "environment/docker-compose.yaml", "environment/codebase.bundle",
                "tests/test.sh", "tests/grade.py", "solution/solve.sh"):
        assert (root / rel).exists(), rel
    assert Path(out["manifest"]).exists()

    toml = tomllib.loads((root / "task.toml").read_text())
    assert toml["name"] == "demo/preview-500s" and toml["environment"]["allow_internet"] is True

    df = (root / "environment" / "Dockerfile").read_text()
    assert "git clone -q /tmp/codebase.bundle /app" in df
    assert "checkout -q 16595d173abc" in df
    for agent in ("logfire-agent", "slack-agent", "jira-agent"):
        assert agent in df
    assert "ODDISH_ROOT=/app/backend" in df

    comp = (root / "environment" / "docker-compose.yaml").read_text()
    assert "networks:" not in comp                       # Harbor contract
    for img in ("logfire-gateway:t", "slack-gateway:t", "jira-gateway:t"):
        assert img in comp
    assert "hostname: jira" in comp                       # linear -> jira hostname
    assert "condition: service_healthy" in comp

    assert "grade.py" in (root / "tests" / "test.sh").read_text()
    man = Path(out["manifest"]).read_text()
    for a in ("nop", "oracle", "gemini-cli", "codex"):
        assert a in man


def test_generate_integration_readback(tmp_path):
    spec = TaskSpec(
        name="demo/triage", kind="integration", incident_t="2026-06-25T00:34:00Z",
        instruction="Triage the alert ticket.",
        surfaces=[Surface("linear", str(tmp_path / "state.json"), "ghcr.io/abundant-ai/jira-gateway:t")],
        verifier=VerifierSpec(kind="readback", checks=[
            {"cmd": "linear issue view ABT-733 --json", "expect_substr": "In Progress"},
        ]))
    out = generate_task(spec, str(tmp_path / "out"))
    ts = Path(out["task_dir"], "tests", "test.sh").read_text()
    assert "linear issue view ABT-733 --json" in ts and "In Progress" in ts
    # integration task has no SUT bundle
    assert not Path(out["task_dir"], "environment", "codebase.bundle").exists()


def test_derive_pr_verifier(tmp_path):
    """The pr_to_task move: empirically find the test that fails@base, passes@head."""
    repo = tmp_path / "r"; repo.mkdir()
    def git(*a): subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True)
    git("init", "-q"); git("config", "user.email", "x@x"); git("config", "user.name", "x")
    (repo / "m.py").write_text("def f():\n    return 1\n")
    (repo / "test_m.py").write_text("from m import f\n\ndef test_f():\n    assert f() == 2\n")
    git("add", "-A"); git("commit", "-qm", "base")
    base = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    (repo / "m.py").write_text("def f():\n    return 2\n")
    git("add", "-A"); git("commit", "-qm", "fix")
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()

    res = derive_pr_verifier(str(repo), base, head, test_cmd=f"{sys.executable} -m pytest")
    assert res["n_f2p"] >= 1
    assert any("test_f" in t for t in res["f2p"])

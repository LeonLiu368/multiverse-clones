"""Publish a captured overlay as a baked gateway image on GHCR.

Bakes a run's overlay into its service's gateway image (using the gateway build scripts) and
`docker push`es it, then records it so the dashboard can list published images per service.
Requires docker + a GHCR login on the host (`gh auth token | docker login ghcr.io ...`)."""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List

SPOINK = Path(__file__).resolve().parents[2]          # repo root (has gateway/)
LOGFIRE_CLONE = Path(os.environ.get("LOGFIRE_CLONE_DIR", str(Path.home() / "projects" / "abundant-logfire-clone")))

DEFAULT_REPO = {"slack": "slack-gateway", "linear": "jira-gateway", "logfire": "logfire-gateway"}


def _bake_cmd(source: str, run_dir: str, image: str, report: Dict[str, Any]) -> List[str]:
    rd = Path(run_dir)
    if source == "slack":
        return ["bash", str(SPOINK / "gateway" / "build.sh"), str(rd / "slack-export"), image]
    if source == "linear":
        proj = report.get("team") or "ABT"
        return ["bash", str(SPOINK / "gateway" / "build_jira.sh"), str(rd / "state.json"), image, proj]
    if source == "logfire":
        return ["bash", str(LOGFIRE_CLONE / "build.sh"), str(rd / "records.json"), image]
    raise RuntimeError(f"{source!r} is not publishable")


def suggest_image(source: str, name: str) -> str:
    repo = DEFAULT_REPO.get(source, f"{source}-gateway")
    tag = re.sub(r"[^a-z0-9._-]+", "-", (name or "snapshot").lower()).strip("-")[:48] or "snapshot"
    return f"ghcr.io/abundant-ai/{repo}:{tag}"


def publish(source: str, run_dir: str, image: str, report: Dict[str, Any]) -> Dict[str, Any]:
    """Bake the overlay into `image` and push it. Returns {image, digest, pushed_at}."""
    cmd = _bake_cmd(source, run_dir, image, report)
    if not Path(cmd[1]).exists():
        raise RuntimeError(f"bake script not found: {cmd[1]} (set LOGFIRE_CLONE_DIR for logfire)")
    b = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    if b.returncode != 0:
        raise RuntimeError(f"bake failed: {(b.stderr or b.stdout)[-600:]}")
    p = subprocess.run(["docker", "push", image], capture_output=True, text=True, timeout=1800)
    if p.returncode != 0:
        raise RuntimeError(f"push failed: {(p.stderr or p.stdout)[-600:]}")
    digest = ""
    for ln in p.stdout.splitlines():
        if "digest:" in ln:
            digest = ln.split("digest:")[1].strip().split()[0]
    return {"image": image, "digest": digest,
            "pushed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


class PublishedRegistry:
    """Persisted list of published images (newest first), deduped by image ref."""
    def __init__(self, path: str):
        self.path = Path(path)
        self.items: List[Dict[str, Any]] = self._load()

    def _load(self) -> List[Dict[str, Any]]:
        try:
            return json.loads(self.path.read_text())
        except Exception:
            return []

    def add(self, rec: Dict[str, Any]) -> None:
        self.items = [i for i in self.items if i.get("image") != rec.get("image")]
        self.items.insert(0, rec)
        self.path.write_text(json.dumps(self.items, indent=2))

    def list(self) -> List[Dict[str, Any]]:
        return self.items

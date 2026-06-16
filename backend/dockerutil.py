"""Thin docker helpers — used ONLY to list/pull images and extract a baked SQLite DB out of one.
The viewer never runs a clone container to serve data; it reads the extracted DB host-side."""
from __future__ import annotations

import shutil
import subprocess
import tempfile

# Where clones bake their prebuilt SQLite. slack-gateway/prod uses /opt/...; slack-seed (FROM
# scratch) uses /...; we probe both.
DB_PATHS = ("/opt/slack.prebuilt.db", "/slack.prebuilt.db")


def _run(args: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, **kw)


def have_docker() -> bool:
    return shutil.which("docker") is not None


def list_images(*name_substrings: str) -> list[str]:
    """Local image tags whose repo contains any of the given substrings (e.g. 'slack-gateway')."""
    if not have_docker():
        return []
    cp = _run(["docker", "images", "--format", "{{.Repository}}:{{.Tag}}"])
    if cp.returncode != 0:
        return []
    out = []
    for line in cp.stdout.splitlines():
        line = line.strip()
        if not line or line.endswith(":<none>"):
            continue
        if any(s in line for s in name_substrings):
            out.append(line)
    return sorted(set(out))


def image_exists(ref: str) -> bool:
    return have_docker() and _run(["docker", "image", "inspect", ref]).returncode == 0


def pull_image(ref: str) -> None:
    if not have_docker():
        raise RuntimeError("docker not available")
    cp = _run(["docker", "pull", ref])
    if cp.returncode != 0:
        raise RuntimeError(f"docker pull {ref} failed:\n{cp.stderr.strip()}")


def extract_db(ref: str, dest_path: str) -> str:
    """Copy the baked prebuilt SQLite DB out of image `ref` to dest_path. Probes known DB paths."""
    if not have_docker():
        raise RuntimeError("docker not available")
    if not image_exists(ref):
        pull_image(ref)
    cid = _run(["docker", "create", ref]).stdout.strip()
    if not cid:
        raise RuntimeError(f"could not create container from {ref}")
    try:
        last_err = ""
        with tempfile.TemporaryDirectory() as tmp:
            for src in DB_PATHS:
                staged = f"{tmp}/db.sqlite"
                cp = _run(["docker", "cp", f"{cid}:{src}", staged])
                if cp.returncode == 0:
                    shutil.copyfile(staged, dest_path)
                    return dest_path
                last_err = cp.stderr.strip()
        raise RuntimeError(
            f"no baked DB found in {ref} at any of {DB_PATHS}. Last error: {last_err}"
        )
    finally:
        _run(["docker", "rm", "-f", cid])

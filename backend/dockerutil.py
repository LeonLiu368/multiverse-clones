"""Thin docker helpers — used ONLY to list/pull images and extract a baked SQLite DB out of one.
The viewer never runs a clone container to serve data; it reads the extracted DB host-side."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

# Where clones bake their prebuilt SQLite. slack-gateway/prod uses /opt/...; slack-seed (FROM
# scratch) uses /...; we probe both.
DB_PATHS = ("/opt/slack.prebuilt.db", "/slack.prebuilt.db")

# The clone images are published linux/amd64-only. On an arm64 host (Apple Silicon), docker defaults
# to the host arch and pull/create fail with "no matching manifest for linux/arm64". We only ever
# copy a file out (never run the container), so forcing amd64 is safe and correct everywhere.
PLATFORM = "linux/amd64"


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
    cp = _run(["docker", "pull", "--platform", PLATFORM, ref])
    if cp.returncode != 0:
        raise RuntimeError(f"docker pull {ref} failed:\n{cp.stderr.strip()}")


def extract_file(ref: str, src_path: str, dest_path: str) -> str:
    """Copy a single file at `src_path` out of image `ref` to dest_path (no container run)."""
    if not have_docker():
        raise RuntimeError("docker not available")
    if not image_exists(ref):
        pull_image(ref)
    cid = _run(["docker", "create", "--platform", PLATFORM, ref]).stdout.strip()
    if not cid:
        raise RuntimeError(f"could not create container from {ref}")
    try:
        cp = _run(["docker", "cp", f"{cid}:{src_path}", dest_path])
        if cp.returncode != 0:
            raise RuntimeError(f"{src_path} not found in {ref}: {cp.stderr.strip()}")
        return dest_path
    finally:
        _run(["docker", "rm", "-f", cid])


def extract_db(ref: str, dest_path: str) -> str:
    """Copy the baked prebuilt SQLite DB out of image `ref` to dest_path. Probes known DB paths."""
    if not have_docker():
        raise RuntimeError("docker not available")
    if not image_exists(ref):
        pull_image(ref)
    cid = _run(["docker", "create", "--platform", PLATFORM, ref]).stdout.strip()
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
            f"no baked Slack DB in {ref} (probed {DB_PATHS}). This looks like a tools-only "
            "agent/main image, not a seed image — load the gateway sidecar (e.g. "
            "ghcr.io/abundant-ai/slack-gateway:<task>) instead. Last error: " + last_err
        )
    finally:
        _run(["docker", "rm", "-f", cid])


# A gateway sidecar (slack-gateway:<task>) bakes its per-task overlay export here, unmerged; boot
# layers it on the prebuilt DB. We extract it so loading the sidecar alone shows the task's real
# merged state.
OVERLAY_PATHS = ("/data/slack-overlay",)


def extract_overlay(ref: str, dest_dir: str) -> str | None:
    """Copy a baked overlay export dir out of image `ref` into dest_dir. Returns the path to the
    extracted overlay dir, or None if the image bakes no overlay."""
    if not have_docker():
        return None
    if not image_exists(ref):
        return None
    cid = _run(["docker", "create", "--platform", PLATFORM, ref]).stdout.strip()
    if not cid:
        return None
    try:
        for src in OVERLAY_PATHS:
            cp = _run(["docker", "cp", f"{cid}:{src}", dest_dir])
            if cp.returncode == 0:
                # docker cp of a dir creates dest_dir/<basename>; return that
                base = src.rstrip("/").rsplit("/", 1)[-1]
                got = f"{dest_dir}/{base}"
                return got if os.path.isdir(got) and os.listdir(got) else None
        return None
    finally:
        _run(["docker", "rm", "-f", cid])

"""Git plumbing for ghc — clone/fetch/push against the local forge.

gh shells out to git for repo clone, pr checkout, etc. We do the same, injecting
the API token into the HTTP remote so it works headless/offline.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from ghclone.config import HostConfig


def clean_remote(cfg: HostConfig, owner: str, repo: str) -> str:
    """http://host/owner/repo.git — NO credentials in the URL.

    gh keeps the token out of the remote and feeds it to git via a credential
    helper (see ensure_credentials). So `git remote -v` shows a plain URL and
    the token never appears in command output.
    """
    u = urlparse(cfg.host)
    return urlunparse((u.scheme, u.netloc, f"/{owner}/{repo}.git", "", "", ""))


def authed_remote(cfg: HostConfig, owner: str, repo: str) -> str:
    """http://<user>:<token>@host/owner/repo.git for headless git over HTTP.

    Used only by operator-side hydration (ghc-hydrate). Agent-facing commands
    use clean_remote + the credential helper so tokens stay out of output.
    """
    u = urlparse(cfg.host)
    user = cfg.user or "git"
    netloc = f"{user}:{cfg.token}@{u.netloc}" if cfg.token else u.netloc
    return urlunparse((u.scheme, netloc, f"/{owner}/{repo}.git", "", "", ""))


def ensure_credentials(cfg: HostConfig) -> None:
    """Wire git to supply our token via the credential store (like gh does).

    Idempotent. Writes one entry per host to ~/.git-credentials and enables the
    `store` helper, so clones/fetches/pushes authenticate without the token ever
    living in a remote URL.
    """
    if not cfg.token:
        return
    u = urlparse(cfg.host)
    user = cfg.user or "git"
    entry = urlunparse((u.scheme, f"{user}:{cfg.token}@{u.netloc}", "", "", "", ""))
    cred_file = Path.home() / ".git-credentials"
    lines = []
    if cred_file.exists():
        lines = [ln for ln in cred_file.read_text().splitlines()
                 if ln.strip() and u.netloc not in ln]
    lines.append(entry)
    cred_file.write_text("\n".join(lines) + "\n")
    subprocess.run(["git", "config", "--global", "credential.helper", "store"],
                   check=False, capture_output=True, text=True)


def run(args: list[str], *, cwd: str | None = None, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=cwd, check=check, text=True,
                          capture_output=True)


def clone(cfg: HostConfig, owner: str, repo: str, dest: str | None = None) -> str:
    dest = dest or repo
    ensure_credentials(cfg)
    run(["git", "clone", clean_remote(cfg, owner, repo), dest])
    return dest


def push_mirror(cfg: HostConfig, owner: str, repo: str, local_dir: str) -> None:
    """Push every ref (branches/tags/pull refs) from local_dir into the forge repo."""
    run(["git", "-C", local_dir, "push", "--mirror", authed_remote(cfg, owner, repo)])


def bundle_create(repo_dir: str, bundle_path: str) -> None:
    # `git -C <repo_dir>` resolves a *relative* bundle path against repo_dir, not the
    # caller's cwd — so a relative out path (e.g. runs/<id>/.../git.bundle) would be
    # written inside _mirror.git and fail (parent dir missing, exit 128). Absolutize it.
    run(["git", "-C", repo_dir, "bundle", "create", str(Path(bundle_path).resolve()), "--all"])


def mirror_clone(src_url: str, dest_dir: str) -> None:
    run(["git", "clone", "--mirror", src_url, dest_dir])


# ---- point-in-time helpers (hydrate --as-of) ----
def commit_timestamp(repo_dir: str, sha: str) -> str:
    """ISO-8601 committer date of a commit (the natural 'T' for a commit)."""
    return run(["git", "-C", repo_dir, "show", "-s", "--format=%cI", sha]).stdout.strip()


def commit_before(repo_dir: str, ref: str, iso_ts: str) -> str:
    """Newest commit on `ref` with committer date <= iso_ts (timestamp -> sha)."""
    out = run(["git", "-C", repo_dir, "rev-list", "-1", f"--before={iso_ts}", ref]).stdout.strip()
    if not out:
        raise RuntimeError(f"no commit on {ref} before {iso_ts}")
    return out


def push_commit_as_branch(cfg, owner: str, repo: str, repo_dir: str, sha: str,
                          branch: str) -> None:
    """Push exactly the history reachable from `sha` as `branch` (the as-of cut)."""
    remote = authed_remote(cfg, owner, repo)
    run(["git", "-C", repo_dir, "push", "--force", remote, f"{sha}:refs/heads/{branch}"])

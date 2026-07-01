"""Engine B, stage 1: freeze a GitHub repo to a local snapshot artifact.

Pulls via the GitHub REST API + a mirror git bundle, writing the layout in
docs/HYDRATION.md. The snapshot is the offline, reproducible, injection-ready
fixture; `apply` replays it into Forgejo with no GitHub access.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import httpx

from ghclone.forge import gitutil

GITHUB_API = "https://api.github.com"


def _client(token: str | None) -> httpx.Client:
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    # transport-level retries cover connection setup; _get() adds retries for mid-flight drops
    return httpx.Client(base_url=GITHUB_API, headers=headers, timeout=60,
                        transport=httpx.HTTPTransport(retries=3))


# transient failures GitHub throws on long snapshots of big repos
_TRANSIENT = (httpx.RemoteProtocolError, httpx.ReadError, httpx.WriteError,
              httpx.ConnectError, httpx.ReadTimeout, httpx.PoolTimeout)


def _get(c: httpx.Client, path: str, params: dict | None = None, tries: int = 6):
    """GET with backoff on transient network drops (e.g. 'Server disconnected without a response')
    and 5xx. Rate-limit 403s are handled by the caller."""
    last = None
    for attempt in range(tries):
        try:
            r = c.get(path, params=params)
        except _TRANSIENT as e:
            last = e
            time.sleep(min(2 ** attempt, 20))
            continue
        if r.status_code >= 500:
            time.sleep(min(2 ** attempt, 20))
            continue
        return r
    raise last if last else RuntimeError(f"GET {path} failed after {tries} tries")


def _paginate(c: httpx.Client, path: str, params: dict | None = None) -> list:
    params = dict(params or {})
    params.setdefault("per_page", 100)
    page, out = 1, []
    while True:
        params["page"] = page
        r = _get(c, path, params=params)
        # honor rate limit
        if r.status_code == 403 and r.headers.get("X-RateLimit-Remaining") == "0":
            reset = int(r.headers.get("X-RateLimit-Reset", "0"))
            time.sleep(max(reset - int(time.time()), 1))
            continue
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        out.extend(batch)
        if len(batch) < params["per_page"]:
            break
        page += 1
    return out


def _wj(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False))


def snapshot(owner_repo: str, out_dir: str, *, token: str | None = None,
             resume: bool = False) -> dict:
    """Capture OWNER/REPO into out_dir. Returns the manifest dict."""
    owner, repo = owner_repo.split("/", 1)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    c = _client(token)

    # 1. repo metadata
    meta = _get(c, f"/repos/{owner}/{repo}")
    meta.raise_for_status()
    meta = meta.json()
    _wj(out / "repo.json", {
        "full_name": meta["full_name"], "description": meta.get("description") or "",
        "private": meta.get("private", False), "default_branch": meta.get("default_branch", "main"),
        "topics": meta.get("topics", []), "created_at": meta.get("created_at"),
        "homepage": meta.get("homepage"),
    })

    # 2. git history → mirror bundle (token-auth clone URL for private repos)
    src = f"https://{token + '@' if token else ''}github.com/{owner}/{repo}.git"
    mirror_dir = out / "_mirror.git"
    if not (resume and (out / "git.bundle").exists()):
        if mirror_dir.exists():
            import shutil
            shutil.rmtree(mirror_dir)
        gitutil.mirror_clone(src, str(mirror_dir))
        gitutil.bundle_create(str(mirror_dir), str(out / "git.bundle"))

    # 3. labels / milestones / releases
    _wj(out / "labels.json", _paginate(c, f"/repos/{owner}/{repo}/labels"))
    _wj(out / "milestones.json", _paginate(c, f"/repos/{owner}/{repo}/milestones", {"state": "all"}))
    _wj(out / "releases.json", _paginate(c, f"/repos/{owner}/{repo}/releases"))

    # 4. issues (issues only; GitHub mixes PRs into /issues, filter them out)
    authors: set[str] = set()
    raw_issues = _paginate(c, f"/repos/{owner}/{repo}/issues", {"state": "all"})
    n_issues = 0
    for it in raw_issues:
        if "pull_request" in it:
            continue
        comments = _paginate(c, f"/repos/{owner}/{repo}/issues/{it['number']}/comments")
        timeline = _paginate(c, f"/repos/{owner}/{repo}/issues/{it['number']}/timeline")
        authors.add((it.get("user") or {}).get("login", ""))
        for cm in comments:
            authors.add((cm.get("user") or {}).get("login", ""))
        _wj(out / "issues" / f"{it['number']:06d}.json",
            {"issue": it, "comments": comments, "timeline": timeline})
        n_issues += 1

    # 5. pull requests (+ reviews, review comments, diff)
    raw_pulls = _paginate(c, f"/repos/{owner}/{repo}/pulls", {"state": "all"})
    n_pulls = 0
    for p in raw_pulls:
        num = p["number"]
        reviews = _paginate(c, f"/repos/{owner}/{repo}/pulls/{num}/reviews")
        review_comments = _paginate(c, f"/repos/{owner}/{repo}/pulls/{num}/comments")
        issue_comments = _paginate(c, f"/repos/{owner}/{repo}/issues/{num}/comments")
        timeline = _paginate(c, f"/repos/{owner}/{repo}/issues/{num}/timeline")
        authors.add((p.get("user") or {}).get("login", ""))
        _wj(out / "pulls" / f"{num:06d}.json", {
            "pull": p, "reviews": reviews, "review_comments": review_comments,
            "issue_comments": issue_comments, "timeline": timeline,
            "base_sha": p["base"]["sha"], "head_sha": p["head"]["sha"],
            "head_ref": p["head"]["ref"], "base_ref": p["base"]["ref"],
        })
        n_pulls += 1

    # 6. users map (default: ghost; edit before apply to map real Forgejo users)
    users_map = {a: {"ghc_login": "", "strategy": "ghost"} for a in sorted(authors) if a}
    _wj(out / "users.map.json", users_map)

    manifest = {
        "source": owner_repo, "tool_version": "0.0.1",
        "counts": {"issues": n_issues, "pulls": n_pulls,
                   "labels": len(json.loads((out / "labels.json").read_text())),
                   "milestones": len(json.loads((out / "milestones.json").read_text())),
                   "releases": len(json.loads((out / "releases.json").read_text())),
                   "authors": len(users_map)},
        "default_branch": meta.get("default_branch", "main"),
    }
    _wj(out / "MANIFEST.json", manifest)
    c.close()
    return manifest

"""Engine B, stage 2: replay a snapshot into Forgejo. Offline — no GitHub access.

Order (so issue/PR indices line up with GitHub):
  repo create -> git push -> labels -> milestones ->
  issues+PRs in one numeric sequence (placeholder the gaps) ->
  comments/reviews in time order -> final state (close/merge) -> releases.

`as_of` (sha or ISO timestamp) hydrates the repo AT a point in time:
  - git: push only history reachable from the commit (timestamp -> newest commit <= T)
  - issues/PRs: include only those created <= T, with state/labels/title reconstructed
    as of T from the timeline (see temporal.py), and comments truncated at T.

Authorship: users.map.json maps github_login -> {ghc_login, strategy}. A mapped
ghc_login is created (admin) and impersonated via Sudo; a 'ghost' author keeps
provenance in a quoted prefix. Every fallback is recorded in the returned report.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from ghclone.config import resolve as resolve_cfg
from ghclone.forge import ForgejoClient, ForgejoError, gitutil
from ghclone.hydrate import temporal


def load_users_map(path: str | None, snapshot_dir: str) -> dict:
    p = Path(path) if path else Path(snapshot_dir) / "users.map.json"
    return json.loads(p.read_text()) if p.exists() else {}


def plan_apply(snapshot_dir: str, into: str, as_of: str | None = None) -> list[str]:
    owner, repo = into.split("/", 1)
    snap = Path(snapshot_dir)
    issues = sorted((snap / "issues").glob("*.json")) if (snap / "issues").exists() else []
    pulls = sorted((snap / "pulls").glob("*.json")) if (snap / "pulls").exists() else []
    cut = f" AS OF {as_of}" if as_of else ""
    return [
        f"create repo {owner}/{repo} from repo.json",
        f"git push history{cut} (reachable-from-commit cut)" if as_of else
        "git clone git.bundle && git push --mirror (history, branches, tags)",
        "create labels.json + milestones.json",
        f"replay {len(issues)} issues + {len(pulls)} PRs in numeric order (gap placeholders){cut}",
        "reconstruct state/labels/title as of T from timeline; truncate comments at T" if as_of
        else "replay comments/reviews in timestamp order, remap authors",
        "apply final state: close/merge",
        "create releases.json",
    ]


def _provenance(body: str, user: dict, when: str | None) -> str:
    login = (user or {}).get("login", "unknown")
    head = f"> _originally by @{login}" + (f" on {when}_" if when else "_")
    return f"{head}\n\n{body or ''}"


class _Authors:
    def __init__(self, base: ForgejoClient, users_map: dict):
        self.base = base
        self.map = users_map
        self._cache: dict[str, ForgejoClient] = {}
        self.created: list[str] = []

    def client_for(self, login: str | None):
        entry = self.map.get(login or "", {})
        target = entry.get("ghc_login")
        if not target:
            return self.base, True
        if target not in self._cache:
            if self.base.get_user(target) is None:
                try:
                    self.base.create_user(username=target, email=f"{target}@local",
                                          password="hydrated-pw-0")
                    self.created.append(target)
                except ForgejoError:
                    pass
            self._cache[target] = self.base.as_user(target)
        return self._cache[target], False


def _resolve_as_of(mirror_dir: str, default_branch: str, as_of: str) -> tuple[datetime, str]:
    """Return (cutoff_datetime, sha). as_of may be a commit sha or an ISO timestamp."""
    looks_ts = ("T" in as_of and "-" in as_of) or as_of.count("-") >= 2
    if looks_ts:
        cutoff = temporal.parse_cutoff(as_of)
        sha = gitutil.commit_before(mirror_dir, default_branch, as_of)
    else:
        sha = as_of
        cutoff = temporal.parse_cutoff(gitutil.commit_timestamp(mirror_dir, sha))
    return cutoff, sha


def apply(snapshot_dir: str, into: str, *, users_map: str | None = None, as_of: str | None = None,
          dry_run: bool = False, client: ForgejoClient | None = None) -> dict:
    steps = plan_apply(snapshot_dir, into, as_of)
    if dry_run:
        return {"into": into, "dry_run": True, "as_of": as_of, "steps": steps}

    snap = Path(snapshot_dir)
    owner, repo = into.split("/", 1)
    c = client or ForgejoClient(resolve_cfg())
    cfg = c.cfg
    meta = json.loads((snap / "repo.json").read_text())
    default_branch = meta.get("default_branch", "main")
    umap = load_users_map(users_map, snapshot_dir)
    authors = _Authors(c, umap)
    report: dict = {"into": into, "as_of": as_of, "cutoff": None, "created_user_count": 0,
                    "issues": 0, "pulls": 0, "placeholders": 0, "pr_fallbacks": 0,
                    "excluded_after_cutoff": 0, "comments": 0, "warnings": []}

    # 1. repo (uninitialized; history comes from the bundle push)
    try:
        c.create_repo(name=repo, private=meta.get("private", False),
                      description=meta.get("description", ""), owner=None,
                      auto_init=False, default_branch=default_branch)
    except ForgejoError as e:
        report["warnings"].append(f"repo create: {e}")
    if meta.get("topics"):
        try:
            c.set_topics(owner, repo, meta["topics"])
        except ForgejoError as e:
            report["warnings"].append(f"topics: {e}")

    # 2. git history (+ resolve as_of cutoff from the same mirror)
    cutoff: datetime | None = None
    bundle = snap / "git.bundle"
    workdir = tempfile.mkdtemp(prefix="ghc-hydrate-")
    mirror = f"{workdir}/m.git"
    try:
        if bundle.exists():
            gitutil.run(["git", "clone", "--mirror", str(bundle), mirror])
            if as_of:
                cutoff, sha = _resolve_as_of(mirror, default_branch, as_of)
                report["cutoff"] = cutoff.isoformat()
                try:
                    gitutil.push_commit_as_branch(cfg, owner, repo, mirror, sha, default_branch)
                except Exception as e:  # noqa: BLE001
                    report["warnings"].append(f"git push (as-of): {e}")
            else:
                try:
                    gitutil.push_mirror(cfg, owner, repo, mirror)
                except Exception as e:  # noqa: BLE001
                    report["warnings"].append(f"git push --mirror: {e}")
        else:
            report["warnings"].append("no git.bundle in snapshot")
            if as_of:
                # timestamp cutoff still applies to issues/PRs even without git
                try:
                    cutoff = temporal.parse_cutoff(as_of)
                    report["cutoff"] = cutoff.isoformat()
                except ValueError:
                    report["warnings"].append("as_of is a sha but no bundle to resolve it")

        _replay_metadata_and_issues(c, authors, owner, repo, snap, cutoff, report)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    report["created_user_count"] = len(authors.created)
    return report


def _replay_metadata_and_issues(c, authors, owner, repo, snap, cutoff, report):
    # labels + milestones
    for lb in json.loads((snap / "labels.json").read_text() or "[]"):
        try:
            c.create_label(owner, repo, name=lb["name"], color="#" + lb.get("color", "ededed"),
                           description=lb.get("description") or "")
        except ForgejoError:
            pass
    for ms in json.loads((snap / "milestones.json").read_text() or "[]"):
        try:
            c.create_milestone(owner, repo, title=ms["title"],
                               description=ms.get("description") or "", state=ms.get("state", "open"))
        except ForgejoError:
            pass

    def _load(d, key):
        out = {}
        p = snap / d
        if p.exists():
            for f in p.glob("*.json"):
                obj = json.loads(f.read_text())
                out[obj[key]["number"]] = obj
        return out

    issues = _load("issues", "issue")
    pulls = _load("pulls", "pull")
    all_nums = sorted(set(issues) | set(pulls))
    max_num = all_nums[-1] if all_nums else 0
    try:
        branches = {b["name"] for b in c.paginate(f"/repos/{owner}/{repo}/branches")}
    except ForgejoError:
        branches = set()

    def _excluded(item) -> bool:
        if cutoff is None:
            return False
        if not temporal.included_at(item, cutoff):
            report["excluded_after_cutoff"] += 1
            return True
        return False

    for n in range(1, max_num + 1):
        if n in issues:
            obj = issues[n]
            it = obj["issue"]
            if _excluded(it):
                _placeholder(c, owner, repo, n, report, note="created after cutoff")
                continue
            recon = temporal.state_at(it, obj.get("timeline"), cutoff) if cutoff else \
                {"state": it.get("state"), "title": it.get("title")}
            cl, prov = authors.client_for((it.get("user") or {}).get("login"))
            body = _provenance(it.get("body") or "", it.get("user"), it.get("created_at")) if prov else (it.get("body") or "")
            try:
                created = cl.create_issue(owner, repo, title=recon["title"], body=body)
                report["issues"] += 1
                _replay_comments(authors, owner, repo, created["number"], obj.get("comments", []), cutoff, report)
                if recon["state"] == "closed":
                    c.edit_issue(owner, repo, created["number"], state="closed")
            except ForgejoError as e:
                report["warnings"].append(f"issue #{n}: {e}")
        elif n in pulls:
            obj = pulls[n]
            p = obj["pull"]
            if _excluded(p):
                _placeholder(c, owner, repo, n, report, note="created after cutoff")
                continue
            recon = temporal.state_at(p, obj.get("timeline"), cutoff, is_pr=True) if cutoff else \
                {"state": p.get("state"), "merged": p.get("merged"), "title": p.get("title")}
            head_ref, base_ref = obj.get("head_ref"), obj.get("base_ref")
            cl, prov = authors.client_for((p.get("user") or {}).get("login"))
            body = _provenance(p.get("body") or "", p.get("user"), p.get("created_at")) if prov else (p.get("body") or "")
            made = False
            if head_ref in branches and base_ref in branches:
                try:
                    created = cl.create_pr(owner, repo, title=recon["title"], head=head_ref, base=base_ref, body=body)
                    report["pulls"] += 1
                    made = True
                    _replay_comments(authors, owner, repo, created["number"], obj.get("issue_comments", []), cutoff, report)
                    if recon.get("merged"):
                        try:
                            c.merge_pr(owner, repo, created["number"])
                        except ForgejoError:
                            c.edit_pr(owner, repo, created["number"], state="closed")
                    elif recon["state"] == "closed":
                        c.edit_pr(owner, repo, created["number"], state="closed")
                except ForgejoError as e:
                    report["warnings"].append(f"pr #{n}: {e}; falling back to issue")
            if not made:
                fb = f"**[migrated PR — head `{head_ref}` unavailable]**\n\n" + body
                try:
                    created = cl.create_issue(owner, repo, title=f"[PR] {recon['title']}", body=fb)
                    c.edit_issue(owner, repo, created["number"], state="closed")
                    report["pr_fallbacks"] += 1
                except ForgejoError as e:
                    report["warnings"].append(f"pr #{n} fallback: {e}")
        else:
            _placeholder(c, owner, repo, n, report)

    # releases
    for rel in json.loads((snap / "releases.json").read_text() or "[]"):
        try:
            c.create_release(owner, repo, tag_name=rel["tag_name"], name=rel.get("name") or "",
                             body=rel.get("body") or "", draft=rel.get("draft", False),
                             prerelease=rel.get("prerelease", False))
        except ForgejoError:
            pass


def _placeholder(c, owner, repo, n, report, note="deleted"):
    try:
        ph = c.create_issue(owner, repo, title=f"[{note} #{n}]",
                            body="_placeholder to preserve numbering_")
        c.edit_issue(owner, repo, ph["number"], state="closed")
        report["placeholders"] += 1
    except ForgejoError as e:
        report["warnings"].append(f"placeholder #{n}: {e}")


def _replay_comments(authors, owner, repo, index, comments, cutoff, report):
    for cm in sorted(comments, key=lambda x: x.get("created_at") or ""):
        if cutoff is not None and not temporal.included_at(cm, cutoff):
            continue
        cl, prov = authors.client_for((cm.get("user") or {}).get("login"))
        body = _provenance(cm.get("body") or "", cm.get("user"), cm.get("created_at")) if prov else (cm.get("body") or "")
        try:
            cl.comment(owner, repo, index, body)
            report["comments"] += 1
        except ForgejoError as e:
            report["warnings"].append(f"comment on #{index}: {e}")

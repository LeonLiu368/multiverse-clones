"""ForgejoClient — the single translation layer between gh-shaped operations
and Forgejo's REST API (Gitea-compatible, Swagger at /api/swagger).

Everything in ghc (CLI and MCP) goes through this client. Keep gh-isms OUT of
here: this speaks Forgejo. The gh->Forgejo concept mapping lives in the command
modules; this is the thin, typed HTTP surface.
"""

from __future__ import annotations

from typing import Any

import httpx

from ghclone.config import HostConfig


class ForgejoError(RuntimeError):
    def __init__(self, status: int, message: str, url: str):
        super().__init__(f"[{status}] {message} ({url})")
        self.status = status
        self.message = message
        self.url = url


class ForgejoClient:
    def __init__(self, cfg: HostConfig, *, timeout: float = 30.0, sudo: str | None = None):
        self.cfg = cfg
        headers = {"Accept": "application/json"}
        if cfg.token:
            headers["Authorization"] = f"token {cfg.token}"
        if sudo:
            # Admin impersonation: act as another user (used by hydration to
            # preserve authorship). Requires the token to belong to an admin.
            headers["Sudo"] = sudo
        self._http = httpx.Client(base_url=cfg.api_base, headers=headers, timeout=timeout)

    def as_user(self, login: str) -> "ForgejoClient":
        """Return a client that impersonates `login` via the Sudo header."""
        return ForgejoClient(self.cfg, sudo=login)

    # ---- low-level ----
    def _req(self, method: str, path: str, *, raw: bool = False, **kw) -> Any:
        r = self._http.request(method, path, **kw)
        if r.status_code >= 400:
            msg = r.text
            try:
                msg = r.json().get("message", msg)
            except Exception:
                pass
            raise ForgejoError(r.status_code, msg, str(r.request.url))
        if raw:
            return r.text
        if r.status_code == 204 or not r.content:
            return None
        return r.json()

    def get(self, path, **kw):
        return self._req("GET", path, **kw)

    def post(self, path, **kw):
        return self._req("POST", path, **kw)

    def patch(self, path, **kw):
        return self._req("PATCH", path, **kw)

    def put(self, path, **kw):
        return self._req("PUT", path, **kw)

    def delete(self, path, **kw):
        return self._req("DELETE", path, **kw)

    def paginate(self, path: str, *, params: dict | None = None, limit: int = 1000) -> list:
        """Follow Forgejo pagination (page/limit) until exhausted or `limit` hit."""
        params = dict(params or {})
        params.setdefault("limit", 50)
        page, out = 1, []
        while len(out) < limit:
            params["page"] = page
            batch = self.get(path, params=params) or []
            if not isinstance(batch, list) or not batch:
                break
            out.extend(batch)
            if len(batch) < params["limit"]:
                break
            page += 1
        return out[:limit]

    # ---- auth / metadata ----
    def whoami(self) -> dict:
        return self.get("/user")

    def version(self) -> dict:
        return self.get("/version")

    def list_tokens(self, user: str) -> list[dict]:
        return self.get(f"/users/{user}/tokens") or []

    # ---- users (hydration: create mapped authors) ----
    def get_user(self, login: str) -> dict | None:
        try:
            return self.get(f"/users/{login}")
        except ForgejoError as e:
            if e.status == 404:
                return None
            raise

    def create_user(self, *, username: str, email: str, password: str,
                    must_change_password: bool = False) -> dict:
        return self.post("/admin/users", json={
            "username": username, "email": email, "password": password,
            "must_change_password": must_change_password,
        })

    # ---- repos ----
    def list_repos(self, *, owner: str | None = None, limit: int = 30) -> list[dict]:
        if owner:
            # try org first, fall back to user namespace
            try:
                return self.paginate(f"/orgs/{owner}/repos", limit=limit)
            except ForgejoError:
                return self.paginate(f"/users/{owner}/repos", limit=limit)
        return self.paginate("/user/repos", limit=limit)

    def get_repo(self, owner: str, repo: str) -> dict:
        return self.get(f"/repos/{owner}/{repo}")

    def create_repo(self, *, name: str, private: bool = False, description: str = "",
                    owner: str | None = None, auto_init: bool = True,
                    default_branch: str = "main") -> dict:
        body = {"name": name, "private": private, "description": description,
                "auto_init": auto_init, "default_branch": default_branch}
        path = f"/orgs/{owner}/repos" if owner else "/user/repos"
        return self.post(path, json=body)

    def edit_repo(self, owner: str, repo: str, **fields) -> dict:
        return self.patch(f"/repos/{owner}/{repo}", json=fields)

    def delete_repo(self, owner: str, repo: str) -> None:
        self.delete(f"/repos/{owner}/{repo}")

    def fork_repo(self, owner: str, repo: str, *, organization: str | None = None) -> dict:
        body = {"organization": organization} if organization else {}
        return self.post(f"/repos/{owner}/{repo}/forks", json=body)

    def set_topics(self, owner: str, repo: str, topics: list[str]) -> None:
        self.put(f"/repos/{owner}/{repo}/topics", json={"topics": topics})

    # ---- branches / contents (PR test + hydration) ----
    def create_branch(self, owner: str, repo: str, *, new_branch: str,
                      old_branch: str | None = None) -> dict:
        body = {"new_branch_name": new_branch}
        if old_branch:
            body["old_branch_name"] = old_branch
        return self.post(f"/repos/{owner}/{repo}/branches", json=body)

    def put_file(self, owner: str, repo: str, path: str, *, content_b64: str,
                 message: str, branch: str | None = None) -> dict:
        body: dict = {"content": content_b64, "message": message}
        if branch:
            body["branch"] = branch
        return self.post(f"/repos/{owner}/{repo}/contents/{path}", json=body)

    # ---- migration / hydration (Engine A) ----
    def migrate_repo(self, *, clone_addr: str, repo_owner: str, repo_name: str,
                     auth_token: str | None = None, mirror: bool = False,
                     issues: bool = True, pull_requests: bool = True, labels: bool = True,
                     milestones: bool = True, releases: bool = True, wiki: bool = True) -> dict:
        body = {
            "clone_addr": clone_addr, "service": "github",
            "repo_owner": repo_owner, "repo_name": repo_name, "mirror": mirror,
            "issues": issues, "pull_requests": pull_requests, "labels": labels,
            "milestones": milestones, "releases": releases, "wiki": wiki,
        }
        if auth_token:
            body["auth_token"] = auth_token
        return self.post("/repos/migrate", json=body)

    # ---- labels ----
    def list_labels(self, owner: str, repo: str) -> list[dict]:
        return self.paginate(f"/repos/{owner}/{repo}/labels")

    def create_label(self, owner: str, repo: str, *, name: str, color: str = "#ededed",
                     description: str = "") -> dict:
        return self.post(f"/repos/{owner}/{repo}/labels",
                         json={"name": name, "color": color, "description": description})

    # ---- milestones ----
    def list_milestones(self, owner: str, repo: str, *, state: str = "all") -> list[dict]:
        return self.paginate(f"/repos/{owner}/{repo}/milestones", params={"state": state})

    def create_milestone(self, owner: str, repo: str, *, title: str, description: str = "",
                         state: str = "open") -> dict:
        return self.post(f"/repos/{owner}/{repo}/milestones",
                         json={"title": title, "description": description, "state": state})

    # ---- issues ----
    def list_issues(self, owner: str, repo: str, *, state: str = "open", labels: str | None = None,
                    milestones: str | None = None, q: str | None = None, assigned: bool = False,
                    created: bool = False, limit: int = 30) -> list[dict]:
        params: dict = {"state": state, "type": "issues"}
        if labels:
            params["labels"] = labels
        if milestones:
            params["milestones"] = milestones
        if q:
            params["q"] = q
        if assigned:
            params["assigned"] = True
        if created:
            params["created"] = True
        return self.paginate(f"/repos/{owner}/{repo}/issues", params=params, limit=limit)

    def get_issue(self, owner: str, repo: str, index: int) -> dict:
        return self.get(f"/repos/{owner}/{repo}/issues/{index}")

    def create_issue(self, owner: str, repo: str, *, title: str, body: str = "",
                     labels: list[int] | None = None, assignees: list[str] | None = None,
                     milestone: int | None = None) -> dict:
        payload: dict = {"title": title, "body": body}
        if labels:
            payload["labels"] = labels
        if assignees:
            payload["assignees"] = assignees
        if milestone:
            payload["milestone"] = milestone
        return self.post(f"/repos/{owner}/{repo}/issues", json=payload)

    def edit_issue(self, owner: str, repo: str, index: int, **fields) -> dict:
        return self.patch(f"/repos/{owner}/{repo}/issues/{index}", json=fields)

    def list_comments(self, owner: str, repo: str, index: int) -> list[dict]:
        return self.paginate(f"/repos/{owner}/{repo}/issues/{index}/comments")

    def comment(self, owner: str, repo: str, index: int, body: str) -> dict:
        return self.post(f"/repos/{owner}/{repo}/issues/{index}/comments", json={"body": body})

    def edit_comment(self, owner: str, repo: str, comment_id: int, body: str) -> dict:
        return self.patch(f"/repos/{owner}/{repo}/issues/comments/{comment_id}", json={"body": body})

    def delete_comment(self, owner: str, repo: str, comment_id: int) -> None:
        self.delete(f"/repos/{owner}/{repo}/issues/comments/{comment_id}")

    # ---- pull requests ----
    def list_prs(self, owner: str, repo: str, *, state: str = "open", limit: int = 30) -> list[dict]:
        return self.paginate(f"/repos/{owner}/{repo}/pulls", params={"state": state}, limit=limit)

    def get_pr(self, owner: str, repo: str, index: int) -> dict:
        return self.get(f"/repos/{owner}/{repo}/pulls/{index}")

    def create_pr(self, owner: str, repo: str, *, title: str, head: str, base: str,
                  body: str = "") -> dict:
        return self.post(f"/repos/{owner}/{repo}/pulls",
                         json={"title": title, "head": head, "base": base, "body": body})

    def edit_pr(self, owner: str, repo: str, index: int, **fields) -> dict:
        return self.patch(f"/repos/{owner}/{repo}/pulls/{index}", json=fields)

    def pr_diff(self, owner: str, repo: str, index: int) -> str:
        return self.get(f"/repos/{owner}/{repo}/pulls/{index}.diff", raw=True)

    def merge_pr(self, owner: str, repo: str, index: int, *, method: str = "merge",
                 title: str | None = None, message: str | None = None) -> None:
        body: dict = {"Do": method}
        if title:
            body["MergeTitleField"] = title
        if message:
            body["MergeMessageField"] = message
        self.post(f"/repos/{owner}/{repo}/pulls/{index}/merge", json=body)

    def create_review(self, owner: str, repo: str, index: int, *, event: str,
                      body: str = "", comments: list[dict] | None = None) -> dict:
        # event: APPROVE | REQUEST_CHANGES | COMMENT | PENDING
        payload: dict = {"event": event, "body": body}
        if comments:
            payload["comments"] = comments
        return self.post(f"/repos/{owner}/{repo}/pulls/{index}/reviews", json=payload)

    def list_reviews(self, owner: str, repo: str, index: int) -> list[dict]:
        return self.paginate(f"/repos/{owner}/{repo}/pulls/{index}/reviews")

    # ---- releases ----
    def list_releases(self, owner: str, repo: str) -> list[dict]:
        return self.paginate(f"/repos/{owner}/{repo}/releases")

    def create_release(self, owner: str, repo: str, *, tag_name: str, name: str = "",
                       body: str = "", draft: bool = False, prerelease: bool = False,
                       target: str | None = None) -> dict:
        payload: dict = {"tag_name": tag_name, "name": name or tag_name, "body": body,
                         "draft": draft, "prerelease": prerelease}
        if target:
            payload["target_commitish"] = target
        return self.post(f"/repos/{owner}/{repo}/releases", json=payload)

    # ---- labels (P1: full CRUD + issue association) ----
    def edit_label(self, owner: str, repo: str, label_id: int, **fields) -> dict:
        return self.patch(f"/repos/{owner}/{repo}/labels/{label_id}", json=fields)

    def delete_label(self, owner: str, repo: str, label_id: int) -> None:
        self.delete(f"/repos/{owner}/{repo}/labels/{label_id}")

    def add_issue_labels(self, owner: str, repo: str, index: int, label_ids: list[int]) -> list[dict]:
        return self.post(f"/repos/{owner}/{repo}/issues/{index}/labels", json={"labels": label_ids})

    def remove_issue_label(self, owner: str, repo: str, index: int, label_id: int) -> None:
        self.delete(f"/repos/{owner}/{repo}/issues/{index}/labels/{label_id}")

    # ---- milestones (P1: edit/delete) ----
    def edit_milestone(self, owner: str, repo: str, milestone_id: int, **fields) -> dict:
        return self.patch(f"/repos/{owner}/{repo}/milestones/{milestone_id}", json=fields)

    def delete_milestone(self, owner: str, repo: str, milestone_id: int) -> None:
        self.delete(f"/repos/{owner}/{repo}/milestones/{milestone_id}")

    # ---- reactions (P1) ----
    def add_reaction(self, owner: str, repo: str, index: int, content: str) -> dict:
        return self.post(f"/repos/{owner}/{repo}/issues/{index}/reactions",
                         json={"content": content})

    def list_reactions(self, owner: str, repo: str, index: int) -> list[dict]:
        return self.get(f"/repos/{owner}/{repo}/issues/{index}/reactions") or []

    def add_comment_reaction(self, owner: str, repo: str, comment_id: int, content: str) -> dict:
        return self.post(f"/repos/{owner}/{repo}/issues/comments/{comment_id}/reactions",
                         json={"content": content})

    # ---- contents (P1: read workflow files / arbitrary files) ----
    def get_contents(self, owner: str, repo: str, path: str, *, ref: str | None = None) -> Any:
        params = {"ref": ref} if ref else None
        return self.get(f"/repos/{owner}/{repo}/contents/{path}", params=params)

    # ---- Actions / Workflows (P1) ----
    def list_workflows(self, owner: str, repo: str, *, ref: str | None = None) -> list[dict]:
        """No list-workflows REST endpoint in Forgejo — enumerate the workflow
        files under .github/workflows and .forgejo/workflows instead."""
        found: list[dict] = []
        for d in (".github/workflows", ".forgejo/workflows"):
            try:
                entries = self.get_contents(owner, repo, d, ref=ref) or []
            except ForgejoError:
                continue
            for e in entries:
                if e.get("type") == "file" and e["name"].endswith((".yml", ".yaml")):
                    found.append({"name": e["name"], "path": e["path"]})
        return found

    def list_runs(self, owner: str, repo: str, *, limit: int = 30) -> list[dict]:
        """Action runs (Forgejo calls them tasks)."""
        data = self.get(f"/repos/{owner}/{repo}/actions/tasks", params={"limit": limit})
        if isinstance(data, dict):
            return data.get("workflow_runs") or data.get("tasks") or []
        return data or []

    def dispatch_workflow(self, owner: str, repo: str, workflow: str, *, ref: str = "main",
                          inputs: dict | None = None) -> None:
        self.post(f"/repos/{owner}/{repo}/actions/workflows/{workflow}/dispatches",
                  json={"ref": ref, "inputs": inputs or {}})

    def runner_registration_token(self, owner: str, repo: str) -> dict:
        return self.get(f"/repos/{owner}/{repo}/actions/runners/registration-token")

    # ---- artifacts (P1: gh run download). Forgejo serves these on the WEB root,
    # not /api/v1 — token auth works there. run is the per-repo run_number. ----
    def _web(self, path: str) -> str:
        return f"{self.cfg.host.rstrip('/')}/{path.lstrip('/')}"

    def resolve_run_number(self, owner: str, repo: str, run: int | str | None = None) -> int:
        runs = self.list_runs(owner, repo, limit=100)
        if run is not None:
            for w in runs:
                if str(w.get("run_number")) == str(run) or str(w.get("id")) == str(run):
                    return int(w["run_number"])
            return int(run)
        if not runs:
            raise ForgejoError(404, "no runs for this repo", f"{owner}/{repo}")
        return int(max(runs, key=lambda w: w.get("run_number") or 0)["run_number"])

    def list_run_artifacts(self, owner: str, repo: str, run_number: int) -> list[dict]:
        r = self._http.get(self._web(f"{owner}/{repo}/actions/runs/{run_number}/artifacts"))
        if r.status_code >= 400:
            raise ForgejoError(r.status_code, r.text, str(r.request.url))
        return (r.json() or {}).get("artifacts", [])

    def download_artifact(self, owner: str, repo: str, run_number: int, name: str) -> bytes:
        r = self._http.get(self._web(f"{owner}/{repo}/actions/runs/{run_number}/artifacts/{name}"),
                           follow_redirects=True)
        if r.status_code >= 400:
            raise ForgejoError(r.status_code, r.text, str(r.request.url))
        return r.content

    # ---- generic API pass-through (gh api) ----
    def raw_api(self, method: str, path: str, *, json_body: Any = None,
                params: dict | None = None) -> Any:
        path = "/" + path.lstrip("/")
        return self._req(method, path, json=json_body, params=params)

    def close(self):
        self._http.close()

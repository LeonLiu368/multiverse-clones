"""GitHub repo export via the REST API (read-only) -> a declarative capture JSON.

Third source for spoink (after Slack + Linear). Mirrors the others: a read-only client,
a fetch, an access/sufficiency report. Pulls a repo's issues + pull requests + comments
with ALL timestamps preserved (created/updated/closed/merged), so a later slice_as_of(T)
is possible. Token from env GITHUB_TOKEN/GH_TOKEN, else `gh auth token`; never logged.

NOTE on the target format: unlike Slack (export dir -> slack-gateway) and Linear
(state.json -> jira-gateway), the GitHub clone (ghc-service) currently seeds from an
*imperative* seed.sh and has no declarative, timestamp-preserving ingest format. So this
emits a clean declarative JSON (the faithful capture); wiring it into a gateway needs a
ghc-service declarative-seed format -- the open gap flagged in the research.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from typing import Any, Dict, Iterator, List, Optional

import httpx

API = "https://api.github.com"


def _token(env_var: str) -> Optional[str]:
    t = os.environ.get(env_var) or os.environ.get("GH_TOKEN")
    if t:
        return t
    try:  # fall back to the gh CLI's stored token
        return subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return None


class GitHubClient:
    """Thin GitHub REST client: bearer auth, Link-header pagination, rate-limit waits."""

    def __init__(self, token: str, *, timeout: float = 60.0):
        self._http = httpx.Client(
            base_url=API, timeout=timeout,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                     "X-GitHub-Api-Version": "2022-11-28"},
        )
        self.rate_limit_stalls = 0

    def close(self) -> None:
        self._http.close()

    def _get(self, url: str, params: Optional[Dict[str, Any]] = None) -> httpx.Response:
        for _ in range(6):
            r = self._http.get(url, params=params)
            if r.status_code == 403 and r.headers.get("X-RateLimit-Remaining") == "0":
                self.rate_limit_stalls += 1
                reset = int(r.headers.get("X-RateLimit-Reset", "0"))
                time.sleep(max(1, reset - int(time.time()) + 1))
                continue
            r.raise_for_status()
            return r
        raise RuntimeError(f"{url}: rate-limited repeatedly")

    def get_json(self, path: str, **params: Any) -> Any:
        return self._get(path, params).json()

    def paginate(self, path: str, **params: Any) -> Iterator[Dict[str, Any]]:
        params.setdefault("per_page", 100)
        r = self._get(path, params)
        while True:
            for item in r.json():
                yield item
            nxt = r.links.get("next", {}).get("url")
            if not nxt:
                break
            r = self._get(nxt)  # next url already carries params/cursor


# --------------------------------------------------------------------------- fetch


def _user(u: Optional[Dict[str, Any]]) -> Optional[str]:
    return (u or {}).get("login")


def fetch_repo(client: GitHubClient, owner: str, repo: str) -> Dict[str, Any]:
    """Pull repo meta + issues + pulls + conversation comments (timestamps preserved)."""
    meta = client.get_json(f"/repos/{owner}/{repo}")
    raw = list(client.paginate(f"/repos/{owner}/{repo}/issues", state="all"))
    issues = [{
        "number": i["number"], "title": i.get("title"), "body": i.get("body") or "",
        "state": i.get("state"), "user": _user(i.get("user")),
        "labels": [l["name"] for l in i.get("labels", [])],
        "assignees": [_user(a) for a in i.get("assignees", [])],
        "created_at": i.get("created_at"), "updated_at": i.get("updated_at"), "closed_at": i.get("closed_at"),
    } for i in raw if "pull_request" not in i]
    pulls = [{
        "number": p["number"], "title": p.get("title"), "body": p.get("body") or "",
        "state": p.get("state"), "user": _user(p.get("user")),
        "head": (p.get("head") or {}).get("ref"), "base": (p.get("base") or {}).get("ref"),
        "merged_at": p.get("merged_at"), "created_at": p.get("created_at"),
        "updated_at": p.get("updated_at"), "closed_at": p.get("closed_at"),
    } for p in client.paginate(f"/repos/{owner}/{repo}/pulls", state="all")]
    comments = [{
        "id": c["id"],
        "number": int((c.get("issue_url") or "").rsplit("/", 1)[-1] or 0),
        "user": _user(c.get("user")), "body": c.get("body") or "",
        "created_at": c.get("created_at"), "updated_at": c.get("updated_at"),
    } for c in client.paginate(f"/repos/{owner}/{repo}/issues/comments")]
    return {
        "repo": {
            "full_name": meta.get("full_name"), "private": meta.get("private"),
            "default_branch": meta.get("default_branch"), "description": meta.get("description"),
            "created_at": meta.get("created_at"), "pushed_at": meta.get("pushed_at"),
        },
        "issues": issues, "pulls": pulls, "comments": comments,
    }


# --------------------------------------------------------------------------- probe / report


def run_probe(client: GitHubClient, owner: str, repo: str) -> List[Dict[str, Any]]:
    out = []
    for name, path in [
        ("repo", f"/repos/{owner}/{repo}"),
        ("issues", f"/repos/{owner}/{repo}/issues"),
        ("pulls", f"/repos/{owner}/{repo}/pulls"),
        ("comments", f"/repos/{owner}/{repo}/issues/comments"),
    ]:
        try:
            client.get_json(path, per_page=1)
            out.append({"method": name, "ok": True, "error": None})
        except Exception as e:
            out.append({"method": name, "ok": False, "error": str(e)[:120]})
    return out


def build_report(probe, data) -> Dict[str, Any]:
    by = {p["method"]: p["ok"] for p in probe}
    return {
        "repo": data["repo"]["full_name"],
        "counts": {"issues": len(data["issues"]), "pulls": len(data["pulls"]), "comments": len(data["comments"])},
        "access_matrix": probe,
        "sufficient": bool(by.get("repo") and by.get("issues") and by.get("pulls")),
    }


# --------------------------------------------------------------------------- CLI


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="spoink.github_export", description="Read-only GitHub repo export -> declarative JSON.")
    ap.add_argument("--repo", required=True, help="owner/name, e.g. abundant-ai/oddish")
    ap.add_argument("--out", default="github.json", help="capture JSON to write")
    ap.add_argument("--report", default=None, help="write report (.md; .json alongside)")
    ap.add_argument("--token-env", default="GITHUB_TOKEN", help="env var holding the token (else gh auth token)")
    args = ap.parse_args(argv)

    token = _token(args.token_env)
    if not token:
        print(f"error: no token in ${args.token_env}/$GH_TOKEN and `gh auth token` failed", file=sys.stderr)
        return 2
    if "/" not in args.repo:
        print("error: --repo must be owner/name", file=sys.stderr)
        return 2
    owner, repo = args.repo.split("/", 1)

    client = GitHubClient(token)
    try:
        data = fetch_repo(client, owner, repo)
        probe = run_probe(client, owner, repo)
        rep = build_report(probe, data)
    finally:
        client.close()

    from pathlib import Path
    Path(args.out).write_text(json.dumps(data, indent=2))
    print(json.dumps({"out": args.out, "repo": rep["repo"], **rep["counts"], "sufficient": rep["sufficient"]}))
    if args.report:
        md = args.report if args.report.endswith(".md") else args.report + ".md"
        lines = [f"# GitHub export -- {rep['repo']}", "",
                 f"**Counts:** {rep['counts']['issues']} issues, {rep['counts']['pulls']} pulls, {rep['counts']['comments']} comments",
                 "", "## Access", "", "| endpoint | ok | error |", "|---|---|---|"]
        lines += [f"| `{p['method']}` | {'yes' if p['ok'] else 'no'} | {p.get('error') or ''} |" for p in probe]
        Path(md).write_text("\n".join(lines))
        Path(md[:-3] + ".json").write_text(json.dumps(rep, indent=2))
        print(f"report: {md}", file=sys.stderr)
    return 0 if rep["sufficient"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""GitHub clone seed viewer — a per-task `seed.sh` of `gh` API calls (ghc-service runs it at boot).
We parse the script into a preview of the repos / issues / PRs / reviews it creates, plus the raw
script. Read-only and best-effort (a gh call it doesn't recognize lands in `other`)."""
from __future__ import annotations

import shlex
from typing import Any

from adapters.fileseed import FileSeedAdapter


def _flags(tokens: list[str]) -> tuple[list[str], dict[str, Any]]:
    """Split `--flag value` / `--flag` (repeated flags → lists) from positional args."""
    pos: list[str] = []
    flags: dict[str, Any] = {}
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t.startswith("--"):
            key = t[2:]
            if i + 1 < len(tokens) and not tokens[i + 1].startswith("--"):
                val: Any = tokens[i + 1]
                i += 2
            else:
                val = True
                i += 1
            if key in flags:
                flags[key] = (flags[key] if isinstance(flags[key], list) else [flags[key]]) + [val]
            else:
                flags[key] = val
        else:
            pos.append(t)
            i += 1
    return pos, flags


def _as_list(v: Any) -> list:
    if v is None or v is True:
        return []
    return v if isinstance(v, list) else [v]


class GithubAdapter(FileSeedAdapter):
    id = "github"
    display_name = "GitHub"
    status = "active"
    ui_module = "github"
    sample_files = ("github.seed.sh",)

    def _parse(self, raw: str, path: str) -> dict[str, Any]:
        repos, issues, prs, reviews, comments, other = [], [], [], [], [], []
        joined = raw.replace("\\\n", " ")  # collapse shell line-continuations before tokenizing
        for line in joined.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or not line.startswith("gh"):
                continue
            try:
                toks = shlex.split(line)
            except ValueError:
                continue
            if len(toks) < 3:
                other.append(line)
                continue
            sub, action, rest = toks[1], toks[2], toks[3:]
            pos, fl = _flags(rest)
            if sub == "repo" and action == "create":
                repos.append({"name": pos[0] if pos else fl.get("name"),
                              "description": fl.get("description", ""),
                              "private": "private" in fl})
            elif sub == "issue" and action == "create":
                issues.append({"repo": fl.get("repo"), "title": fl.get("title", ""),
                               "body": fl.get("body", ""), "labels": _as_list(fl.get("label")),
                               "assignees": _as_list(fl.get("assignee"))})
            elif sub == "pr" and action == "create":
                prs.append({"repo": fl.get("repo"), "title": fl.get("title", ""),
                            "body": fl.get("body", ""), "head": fl.get("head"), "base": fl.get("base")})
            elif sub == "pr" and action == "review":
                state = ("approved" if "approve" in fl else "changes_requested"
                         if "request-changes" in fl else "commented")
                reviews.append({"pr": pos[0] if pos else None, "repo": fl.get("repo"),
                                "state": state, "body": fl.get("body", "")})
            elif sub in ("issue", "pr") and action == "comment":
                comments.append({"on": f"{sub} {pos[0] if pos else ''}".strip(), "repo": fl.get("repo"),
                                 "body": fl.get("body", "")})
            else:
                other.append(line)
        return {
            "repos": repos, "issues": issues, "prs": prs, "reviews": reviews,
            "comments": comments, "other": other, "raw": raw,
            "stats": {"repos": len(repos), "issues": len(issues), "prs": len(prs),
                      "reviews": len(reviews), "comments": len(comments)},
        }

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any


def safe_branch_name(identifier: str, title: str, actor: str = "agent") -> str:
    clean_title = re.sub(r"^(critical\s+bug|bug|task|story|follow-up):\s*", "", title, flags=re.I)
    text = f"{identifier}-{clean_title}".lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    text = re.sub(r"-+", "-", text)
    return f"{actor}/{text[:96].strip('-')}"


def current_branch(cwd: str | Path = ".") -> str | None:
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError:
        return None
    branch = result.stdout.strip()
    return branch or None


def recent_commits(cwd: str | Path = ".", limit: int = 5) -> list[dict[str, str]]:
    try:
        result = subprocess.run(
            ["git", "log", f"-{limit}", "--pretty=%H%x00%s"],
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError:
        return []
    commits = []
    for line in result.stdout.splitlines():
        if "\0" in line:
            sha, subject = line.split("\0", 1)
            commits.append({"sha": sha, "subject": subject})
    return commits


def pr_receipt(issue: dict[str, Any], *, cwd: str | Path = ".", create: bool = False) -> dict[str, Any]:
    title = f"{issue['identifier']}: {issue['title']}"
    body = "\n".join(
        [
            f"## Issue",
            f"{issue['identifier']} - {issue['title']}",
            "",
            "## Context",
            issue.get("description", ""),
            "",
            "## Validation",
            "- [ ] Tests updated",
            "- [ ] Agent verified workflow",
        ]
    )
    return {
        "title": title,
        "body": body,
        "branch": current_branch(cwd),
        "commits": recent_commits(cwd),
        "dry_run": not create,
        "would_run": ["gh", "pr", "create", "--title", title, "--body", body],
    }

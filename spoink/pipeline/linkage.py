"""Incident → fix-PR linkage (the crux of incident-first grounding).

An incident feed (linear_sev / slack_incident / logfire_anomaly) yields a candidate whose captured
surface IS the incident, but with NO code oracle. To grade it as a real SWE/DevOps task we must find
the PR that RESOLVED it — that gives the SUT codebase + the F2P test contract.

Empirically (abundant-ai, 2026-07): explicit cross-linking is sparse — ~3% of SEV issues carry a
direct PR link, and PRs rarely back-reference a ticket. So linkage is BEST-EFFORT and low-yield:
we extract whatever explicit references exist (Linear GitHub-integration attachments, PR URLs pasted
into the description/comments), and report honestly when none is found (the candidate stays an
ungradeable diagnosis, or is skipped). We do NOT guess a link from time alone — a false link makes a
task whose "fix" doesn't resolve the incident, which is worse than no task.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

# github.com/<owner>/<repo>/pull/<n>  — the canonical PR reference we trust
_PR_URL = re.compile(r"github\.com/([\w.-]+)/([\w.-]+)/pull/(\d+)", re.I)
# "<owner>/<repo>#<n>" shorthand (GitHub renders it as a PR/issue link)
_PR_SHORT = re.compile(r"\b([\w.-]+)/([\w.-]+)#(\d+)\b")


class PRRef(Dict[str, Any]):
    """{owner, repo, number, via} — a resolved fix-PR reference and where we found it."""


def _refs_in(text: str, via: str) -> List[PRRef]:
    out: List[PRRef] = []
    for m in _PR_URL.finditer(text or ""):
        out.append(PRRef(owner=m.group(1), repo=m.group(2), number=int(m.group(3)), via=via))
    for m in _PR_SHORT.finditer(text or ""):
        # skip bare "#123" already covered by URL matches; require an owner/repo shape
        out.append(PRRef(owner=m.group(1), repo=m.group(2), number=int(m.group(3)), via=via + ":short"))
    return out


def prs_for_linear_issue(issue: Dict[str, Any]) -> List[PRRef]:
    """Extract fix-PR references from a Linear issue's attachments, description, and comments.
    Requires the SEV query to fetch `attachments{nodes{url title sourceType}}` and
    `comments{nodes{body}}` (see discover.Q_LINEAR_SEV). Deduped, attachment links ranked first
    (the GitHub integration link is the most trustworthy signal)."""
    found: List[PRRef] = []
    for a in (issue.get("attachments") or {}).get("nodes", []):
        found += _refs_in((a.get("url") or "") + " " + (a.get("title") or ""), "attachment")
    found += _refs_in(issue.get("description") or "", "description")
    for c in (issue.get("comments") or {}).get("nodes", []):
        found += _refs_in(c.get("body") or "", "comment")
    # dedupe by (owner, repo, number); keep the highest-trust `via` (attachment > description > comment)
    rank = {"attachment": 0, "description": 1, "comment": 2}
    best: Dict[tuple, PRRef] = {}
    for r in found:
        k = (r["owner"].lower(), r["repo"].lower(), r["number"])
        cur = best.get(k)
        if cur is None or rank.get(r["via"].split(":")[0], 9) < rank.get(cur["via"].split(":")[0], 9):
            best[k] = r
    return sorted(best.values(), key=lambda r: (rank.get(r["via"].split(":")[0], 9), r["number"]))


def best_fix_pr(issue: Dict[str, Any], prefer_owner: Optional[str] = None) -> Optional[PRRef]:
    """Pick the single most-likely fix PR for an incident (highest-trust source; prefer an owner
    when the incident's team maps to a known org). Returns None when nothing explicit is linked —
    the caller must treat that as 'not gradeable', not fabricate a link."""
    refs = prs_for_linear_issue(issue)
    if not refs:
        return None
    if prefer_owner:
        owned = [r for r in refs if r["owner"].lower() == prefer_owner.lower()]
        if owned:
            return owned[0]
    return refs[0]

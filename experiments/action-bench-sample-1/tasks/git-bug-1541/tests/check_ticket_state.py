#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

state_path = Path("/var/lib/ticketvector/state.json")
repo_path = Path("/app/repo")
metadata = json.loads(Path("/tests/test_metadata.json").read_text(encoding="utf-8"))
state = json.loads(state_path.read_text(encoding="utf-8"))
primary_id = metadata["ticketvector"]["primary_issue"]
issues = {issue["identifier"]: issue for issue in state.get("issues", [])}
primary = issues.get(primary_id)
failures: list[str] = []

# The verifier container runs as a different user than the one that owns the
# checkout; mark the repo safe before resolving anything in it.
subprocess.run(
    ["git", "config", "--global", "--add", "safe.directory", str(repo_path)],
    capture_output=True,
)


def user_handles(issue: dict) -> set[str]:
    return {str(user.get("handle", "")) for user in issue.get("assignees", [])}


def resolve_commit(ref: str) -> str | None:
    """Resolve ref to a full commit sha that exists in the repo, else None."""
    result = subprocess.run(
        ["git", "-C", str(repo_path), "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() or None


if primary is None:
    failures.append(f"missing primary issue {primary_id}")
else:
    if (primary.get("state") or {}).get("name") != "In Review":
        failures.append(f"{primary_id} is not In Review")
    if "agent" not in user_handles(primary):
        failures.append(f"{primary_id} is not assigned to agent")
    agent_comments = [
        c for c in state.get("comments", {}).get(primary_id, [])
        if (c.get("author") or {}).get("handle") == "agent"
    ]
    if not any(any(word in c.get("body", "").lower() for word in ["investigat", "fixed", "regression", "verified", "complete"]) for c in agent_comments):
        failures.append(f"{primary_id} lacks an agent investigation/completion comment")

    # Commit evidence must point at a real commit in the repo, and at least one
    # linked commit must be the agent's own work rather than the snapshot the
    # environment ships with.
    rev_list = subprocess.run(
        ["git", "-C", str(repo_path), "rev-list", "--max-parents=0", "HEAD"],
        capture_output=True,
        text=True,
    )
    snapshot_shas = {line.strip() for line in rev_list.stdout.splitlines() if line.strip()}
    linked_refs = [
        str(link.get("url", ""))[len("commit:"):]
        for link in state.get("links", {}).get(primary_id, [])
        if str(link.get("url", "")).startswith("commit:")
    ]
    resolved = [sha for sha in (resolve_commit(ref) for ref in linked_refs if ref) if sha]
    if not resolved:
        failures.append(f"{primary_id} lacks a commit link that resolves to a commit in the repo")
    elif all(sha in snapshot_shas for sha in resolved):
        failures.append(f"{primary_id} commit link points at the starting snapshot, not the agent's work")

    # The ticket must have been worked through the tracker in order: assigned
    # to the agent no later than the move to In Progress, and In Progress
    # before the final move to In Review. Only the tracker API appends to
    # history, and it appends in event order, so index order is event order.
    primary_history = state.get("history", {}).get(primary_id, [])
    updates = [item for item in primary_history if item.get("action") == "issue.update"]
    first_in_progress = None
    first_in_review = None
    first_assigned = None
    for idx, item in enumerate(updates):
        after = item.get("after") or {}
        state_name = (after.get("state") or {}).get("name")
        handles = {str(u.get("handle", "")) for u in after.get("assignees", [])}
        if first_in_progress is None and state_name == "In Progress":
            first_in_progress = idx
        if first_in_review is None and state_name == "In Review":
            first_in_review = idx
        if first_assigned is None and "agent" in handles:
            first_assigned = idx
    if first_in_progress is None:
        failures.append(f"{primary_id} was not started through the tracker")
    if first_in_review is None:
        failures.append(f"{primary_id} was not moved to review through the tracker")
    if first_in_progress is not None and first_in_review is not None and first_in_review < first_in_progress:
        failures.append(f"{primary_id} was moved to review before being started")
    if first_in_progress is not None and (first_assigned is None or first_assigned > first_in_progress):
        failures.append(f"{primary_id} was not assigned to the agent when work started")

    receipts = []
    receipt_dir = repo_path / ".ticketvector" / "receipts"
    if receipt_dir.exists():
        for path in sorted(receipt_dir.glob("*.json")):
            receipts.append(json.loads(path.read_text(encoding="utf-8")))
    if not any(r.get("action") == "issue.pr" and r.get("target") == primary_id and r.get("dry_run") is True for r in receipts):
        failures.append(f"{primary_id} lacks ticketvector PR receipt evidence")

for identifier, issue in issues.items():
    if identifier == primary_id:
        continue
    if state.get("history", {}).get(identifier):
        failures.append(f"unrelated issue mutated: {identifier}")
    if any((c.get("author") or {}).get("handle") == "agent" for c in state.get("comments", {}).get(identifier, [])):
        failures.append(f"unrelated issue received agent comment: {identifier}")
    if any(str(link.get("url", "")).startswith("commit:") for link in state.get("links", {}).get(identifier, [])):
        failures.append(f"unrelated issue received commit evidence: {identifier}")

if failures:
    print(json.dumps({"ok": False, "failures": failures}, indent=2), file=sys.stderr)
    sys.exit(1)
print(json.dumps({"ok": True, "primary_issue": primary_id, "checks": ["state", "assignee", "comment", "commit", "ordering", "pr", "unrelated"]}))

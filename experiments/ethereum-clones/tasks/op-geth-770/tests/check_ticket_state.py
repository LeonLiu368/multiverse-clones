#!/usr/bin/env python3
from __future__ import annotations

import json
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


def user_handles(issue: dict) -> set[str]:
    return {str(user.get("handle", "")) for user in issue.get("assignees", [])}


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
    primary_links = state.get("links", {}).get(primary_id, [])
    if not any(str(link.get("url", "")).startswith("commit:") and len(str(link.get("url", ""))) >= 14 for link in primary_links):
        failures.append(f"{primary_id} lacks commit evidence")
    primary_history = state.get("history", {}).get(primary_id, [])
    history_states = [
        ((item.get("after") or {}).get("state") or {}).get("name")
        for item in primary_history
        if item.get("action") == "issue.update"
    ]
    if "In Progress" not in history_states:
        failures.append(f"{primary_id} was not started through the tracker")
    if "In Review" not in history_states:
        failures.append(f"{primary_id} was not moved to review through the tracker")
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
print(json.dumps({"ok": True, "primary_issue": primary_id, "checks": ["state", "assignee", "comment", "commit", "pr", "unrelated"]}))

from __future__ import annotations

import copy
import json
import os
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_STATE_FILE = "/data/sentry-clone/state.json"
DEFAULT_RUNTIME_STATE_FILE = "/var/lib/sentry-clone/state.json"


class StateError(ValueError):
    pass


REQUIRED_TOP_LEVEL = {
    "meta": dict,
    "users": list,
    "teams": list,
    "projects": list,
    "releases": list,
    "issues": list,
    "events": list,
    "ownership_rules": list,
    "comments": list,
    "activity": list,
    "mutation_log": list,
}

OPTIONAL_TOP_LEVEL = {"deploys": list, "commits": list}


def state_file_from_env() -> Path:
    return Path(os.environ.get("SENTRY_CLONE_STATE_FILE", DEFAULT_STATE_FILE))


def runtime_state_file_from_env() -> Path:
    return Path(os.environ.get("SENTRY_CLONE_RUNTIME_STATE_FILE", DEFAULT_RUNTIME_STATE_FILE))


def validate_state(state: dict[str, Any]) -> None:
    if not isinstance(state, dict):
        raise StateError("state root must be an object")
    for key, expected_type in REQUIRED_TOP_LEVEL.items():
        if key not in state:
            raise StateError(f"missing required state key: {key}")
        if not isinstance(state[key], expected_type):
            raise StateError(f"state.{key} must be {expected_type.__name__}")
    for key, expected_type in OPTIONAL_TOP_LEVEL.items():
        state.setdefault(key, [])
        if not isinstance(state[key], expected_type):
            raise StateError(f"state.{key} must be {expected_type.__name__}")

    org = state["meta"].get("organization")
    if not isinstance(org, str) or not org:
        raise StateError("meta.organization is required")

    _require_unique("teams", state["teams"], "slug")
    _require_unique("projects", state["projects"], "slug")
    _require_unique("issues", state["issues"], "id")
    _require_unique("events", state["events"], "id")

    projects = {item["slug"] for item in state["projects"]}
    issues = {str(item["id"]) for item in state["issues"]}
    for release in state["releases"]:
        project_slug = release.get("project_slug")
        if project_slug not in projects:
            raise StateError(f"release project not found: {project_slug}")
    for issue in state["issues"]:
        project_slug = issue.get("project_slug")
        if project_slug not in projects:
            raise StateError(f"issue project not found: {project_slug}")
    for event in state["events"]:
        issue_id = str(event.get("issue_id"))
        project_slug = event.get("project_slug")
        if issue_id not in issues:
            raise StateError(f"event issue not found: {issue_id}")
        if project_slug not in projects:
            raise StateError(f"event project not found: {project_slug}")


def _require_unique(name: str, items: list[dict[str, Any]], key: str) -> None:
    seen: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise StateError(f"{name}[{index}] must be an object")
        value = item.get(key)
        if not isinstance(value, str) or not value:
            raise StateError(f"{name}[{index}].{key} is required")
        if value in seen:
            raise StateError(f"duplicate {name} {key}: {value}")
        seen.add(value)


def load_state(path: str | Path | None = None) -> dict[str, Any]:
    state_path = Path(path) if path else state_file_from_env()
    with state_path.open("r", encoding="utf-8") as handle:
        state = json.load(handle)
    validate_state(state)
    return state


@dataclass
class SentryStore:
    state: dict[str, Any]
    runtime_state_path: Path | None = None

    def __post_init__(self) -> None:
        validate_state(self.state)
        self._lock = threading.RLock()
        self._next_comment_id = self._compute_next_comment_id()

    @classmethod
    def from_file(cls, path: str | Path | None = None) -> "SentryStore":
        return cls(load_state(path))

    @classmethod
    def from_runtime(
        cls,
        seed_path: str | Path | None = None,
        runtime_path: str | Path | None = None,
    ) -> "SentryStore":
        seed = Path(seed_path) if seed_path else state_file_from_env()
        runtime = Path(runtime_path) if runtime_path else runtime_state_file_from_env()
        if runtime.exists():
            state = load_state(runtime)
        else:
            state = load_state(seed)
            _write_state_atomic(runtime, state)
        return cls(state, runtime_state_path=runtime)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self.state)

    def meta_now(self) -> str:
        return str(self.state.get("meta", {}).get("now") or "1970-01-01T00:00:00Z")

    def org_slug(self) -> str:
        return str(self.state["meta"].get("organization") or "acme")

    def current_user(self) -> dict[str, Any]:
        users = self.state.get("users") or []
        if users:
            user = copy.deepcopy(users[0])
        else:
            user = {"id": "u-agent", "email": "agent@example.local", "name": "Agent User"}
        user.setdefault("username", user.get("email", "agent@example.local"))
        return user

    def organizations(self) -> list[dict[str, Any]]:
        slug = self.org_slug()
        return [{"id": slug, "slug": slug, "name": slug.title()}]

    def teams(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self.state["teams"])

    def projects(self, org_slug: str | None = None) -> list[dict[str, Any]]:
        self._check_org(org_slug)
        return copy.deepcopy(self.state["projects"])

    def project(self, project_slug: str, org_slug: str | None = None) -> dict[str, Any] | None:
        self._check_org(org_slug)
        for project in self.state["projects"]:
            if project.get("slug") == project_slug:
                return copy.deepcopy(project)
        return None

    def issues(self, org_slug: str | None = None, project_slug: str | None = None) -> list[dict[str, Any]]:
        self._check_org(org_slug)
        items = self.state["issues"]
        if project_slug:
            items = [item for item in items if item.get("project_slug") == project_slug]
        return copy.deepcopy(items)

    def issue(self, issue_ref: str) -> dict[str, Any] | None:
        for issue in self.state["issues"]:
            if str(issue.get("id")) == str(issue_ref) or str(issue.get("shortId")) == str(issue_ref):
                return copy.deepcopy(issue)
        return None

    def events_for_issue(self, issue_ref: str) -> list[dict[str, Any]]:
        issue = self.issue(issue_ref)
        if not issue:
            return []
        issue_id = str(issue["id"])
        events = [item for item in self.state["events"] if str(item.get("issue_id")) == issue_id]
        return sorted(copy.deepcopy(events), key=lambda item: str(item.get("timestamp", "")), reverse=True)

    def latest_event(self, issue_ref: str) -> dict[str, Any] | None:
        issue = self.issue(issue_ref)
        if not issue:
            return None
        latest_id = issue.get("latestEventId")
        if latest_id:
            event = self.event(str(latest_id))
            if event:
                return event
        events = self.events_for_issue(issue_ref)
        return events[0] if events else None

    def event(self, event_id: str, project_slug: str | None = None) -> dict[str, Any] | None:
        for event in self.state["events"]:
            if str(event.get("id")) == str(event_id) and (not project_slug or event.get("project_slug") == project_slug):
                return copy.deepcopy(event)
        return None

    def releases(self, org_slug: str | None = None, project_slug: str | None = None) -> list[dict[str, Any]]:
        self._check_org(org_slug)
        items = self.state["releases"]
        if project_slug:
            items = [item for item in items if item.get("project_slug") == project_slug]
        return copy.deepcopy(items)

    def release(self, version: str, org_slug: str | None = None, project_slug: str | None = None) -> dict[str, Any] | None:
        self._check_org(org_slug)
        for release in self.state["releases"]:
            if release.get("version") == version and (not project_slug or release.get("project_slug") == project_slug):
                return copy.deepcopy(release)
        return None

    def ownership_rules(self, project_slug: str | None = None) -> list[dict[str, Any]]:
        rules = self.state.get("ownership_rules", [])
        if project_slug:
            rules = [rule for rule in rules if rule.get("project_slug") == project_slug]
        return copy.deepcopy(rules)

    def comments(self, issue_ref: str) -> list[dict[str, Any]]:
        issue = self.issue(issue_ref)
        if not issue:
            return []
        issue_id = str(issue["id"])
        return copy.deepcopy([item for item in self.state["comments"] if str(item.get("issue_id")) == issue_id])

    def activity(self, issue_ref: str) -> list[dict[str, Any]]:
        issue = self.issue(issue_ref)
        if not issue:
            return []
        issue_id = str(issue["id"])
        return copy.deepcopy([item for item in self.state["activity"] if str(item.get("issue_id")) == issue_id])

    def mutation_log(self) -> list[dict[str, Any]]:
        with self._lock:
            return copy.deepcopy(self.state["mutation_log"])

    def add_comment(self, issue_ref: str, text: str, actor: str = "agent") -> dict[str, Any]:
        if not text:
            raise ValueError("comment text is required")
        with self._lock:
            issue = self._issue_ref_locked(issue_ref)
            before = copy.deepcopy(self.comments(issue["id"]))
            comment = {
                "id": f"comment-{self._next_comment_id}",
                "issue_id": str(issue["id"]),
                "user": actor,
                "text": text,
                "dateCreated": self.meta_now(),
            }
            self._next_comment_id += 1
            self.state["comments"].append(comment)
            self._append_activity_locked(issue, "comment", {"text": text, "comment_id": comment["id"]}, actor)
            self._record_mutation_locked("issue.comment", f"issue:{issue['id']}", before, self.comments(issue["id"]), actor)
            self._persist_locked()
            return copy.deepcopy(comment)

    def assign_issue(self, issue_ref: str, assignee: dict[str, Any], actor: str = "agent") -> dict[str, Any]:
        with self._lock:
            issue = self._issue_ref_locked(issue_ref)
            before = copy.deepcopy(issue)
            issue["assignedTo"] = copy.deepcopy(assignee)
            self._append_activity_locked(issue, "assigned", {"assignedTo": assignee}, actor)
            self._record_mutation_locked("issue.assign", f"issue:{issue['id']}", before, issue, actor)
            self._persist_locked()
            return copy.deepcopy(issue)

    def update_issue(self, issue_ref: str, changes: dict[str, Any], actor: str = "agent") -> dict[str, Any]:
        allowed = {"status", "substatus", "priority", "assignedTo", "resolvedInRelease", "ignoreReason", "linkedEvidence", "regressed"}
        filtered = {key: copy.deepcopy(value) for key, value in changes.items() if key in allowed}
        if not filtered:
            raise ValueError("no supported issue fields supplied")
        with self._lock:
            issue = self._issue_ref_locked(issue_ref)
            before = copy.deepcopy(issue)
            issue.update(filtered)
            action = _status_action(before, issue)
            self._append_activity_locked(issue, action, filtered, actor)
            self._record_mutation_locked(f"issue.{action}", f"issue:{issue['id']}", before, issue, actor)
            self._persist_locked()
            return copy.deepcopy(issue)

    def set_status(
        self,
        issue_ref: str,
        status: str,
        *,
        substatus: str | None = None,
        resolved_in_release: str | None = None,
        ignore_reason: str | None = None,
        actor: str = "agent",
    ) -> dict[str, Any]:
        changes: dict[str, Any] = {"status": status}
        if substatus is not None:
            changes["substatus"] = substatus
        if resolved_in_release is not None:
            changes["resolvedInRelease"] = resolved_in_release
        if ignore_reason is not None:
            changes["ignoreReason"] = ignore_reason
        if status == "unresolved":
            changes.setdefault("substatus", "ongoing")
        return self.update_issue(issue_ref, changes, actor=actor)

    def _issue_ref_locked(self, issue_ref: str) -> dict[str, Any]:
        for issue in self.state["issues"]:
            if str(issue.get("id")) == str(issue_ref) or str(issue.get("shortId")) == str(issue_ref):
                return issue
        raise KeyError(f"issue not found: {issue_ref}")

    def _append_activity_locked(self, issue: dict[str, Any], action: str, data: dict[str, Any], actor: str) -> None:
        self.state["activity"].append(
            {
                "id": f"activity-{len(self.state['activity']) + 1}",
                "issue_id": str(issue["id"]),
                "user": actor,
                "type": action,
                "data": copy.deepcopy(data),
                "dateCreated": self.meta_now(),
            }
        )

    def _record_mutation_locked(self, action: str, target: str, before: Any, after: Any, actor: str) -> None:
        self.state["mutation_log"].append(
            {
                "id": str(len(self.state["mutation_log"]) + 1),
                "ts": self.meta_now(),
                "actor": actor,
                "action": action,
                "target": target,
                "before": copy.deepcopy(before),
                "after": copy.deepcopy(after),
            }
        )

    def _compute_next_comment_id(self) -> int:
        ids: list[int] = []
        for comment in self.state.get("comments", []):
            value = str(comment.get("id", ""))
            if value.startswith("comment-") and value.removeprefix("comment-").isdigit():
                ids.append(int(value.removeprefix("comment-")))
        return max(ids, default=0) + 1

    def _persist_locked(self) -> None:
        if self.runtime_state_path is not None:
            _write_state_atomic(self.runtime_state_path, self.state)

    def _check_org(self, org_slug: str | None) -> None:
        if org_slug and org_slug != self.org_slug():
            raise KeyError(f"organization not found: {org_slug}")


def _status_action(before: dict[str, Any], after: dict[str, Any]) -> str:
    if after.get("assignedTo") != before.get("assignedTo"):
        return "assign"
    status = after.get("status")
    if status != before.get("status"):
        if status == "resolved":
            return "resolve"
        if status == "ignored":
            return "ignore"
        if status == "unresolved":
            return "reopen"
    if after.get("regressed") is True:
        return "regress"
    return "update"


def _write_state_atomic(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(state, handle, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise

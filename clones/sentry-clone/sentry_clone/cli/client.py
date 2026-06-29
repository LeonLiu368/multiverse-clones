from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


DEFAULT_URL = "http://sentry"
DEFAULT_TOKEN = "test-token-acme-eval"
DEFAULT_ORG = "acme"


class SentryClientError(RuntimeError):
    exit_code = 1


class NotFoundError(SentryClientError):
    exit_code = 2


class AuthConfigError(SentryClientError):
    exit_code = 3


class BackendUnavailableError(SentryClientError):
    exit_code = 5


class UnsupportedCommandError(SentryClientError):
    exit_code = 6


def _base_url() -> str:
    return (os.environ.get("SENTRY_URL") or DEFAULT_URL).rstrip("/")


def _token() -> str:
    return os.environ.get("SENTRY_AUTH_TOKEN") or DEFAULT_TOKEN


def _org() -> str:
    return os.environ.get("SENTRY_ORG") or DEFAULT_ORG


def _admin_token() -> str:
    token = os.environ.get("SENTRY_CLONE_ADMIN_TOKEN")
    if not token:
        raise AuthConfigError("SENTRY_CLONE_ADMIN_TOKEN is required for sentry-clonectl")
    return token


class SentryClient:
    def __init__(self, base_url: str | None = None, token: str | None = None, org: str | None = None):
        self.base_url = (base_url or _base_url()).rstrip("/")
        self.token = token or _token()
        self.org = org or _org()

    def request(self, method: str, path: str, *, params: dict[str, Any] | None = None, payload: dict[str, Any] | None = None) -> Any:
        url = self.base_url + path
        if params:
            query = urllib.parse.urlencode({key: value for key, value in params.items() if value is not None})
            if query:
                url += "?" + query
        data = None
        headers = {"Accept": "application/json", "Authorization": f"Bearer {self.token}"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                body = response.read().decode("utf-8")
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            message = _error_message(body) or exc.reason
            if exc.code in (401, 403):
                raise AuthConfigError(message)
            if exc.code == 404:
                raise NotFoundError(message)
            if exc.code >= 500:
                raise BackendUnavailableError(message)
            raise SentryClientError(message)
        except urllib.error.URLError as exc:
            raise BackendUnavailableError(str(exc.reason)) from exc

    def health(self) -> dict[str, Any]:
        try:
            with urllib.request.urlopen(self.base_url + "/api/healthz", timeout=5) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise BackendUnavailableError(str(exc.reason)) from exc

    def config_check(self) -> dict[str, Any]:
        return {"ok": True, "url": self.base_url, "org": self.org, "token_configured": bool(self.token), "health": self.health(), "user": self.whoami()}

    def whoami(self) -> dict[str, Any]:
        return self.request("GET", "/api/0/user")

    def organizations(self) -> list[dict[str, Any]]:
        return self.request("GET", "/api/0/organizations/")

    def projects(self, org: str | None = None) -> list[dict[str, Any]]:
        return self.request("GET", f"/api/0/organizations/{quote(org or self.org)}/projects/")

    def project(self, project_slug: str, org: str | None = None) -> dict[str, Any]:
        return self.request("GET", f"/api/0/projects/{quote(org or self.org)}/{quote(project_slug)}/")

    def issues(self, *, project: str | None = None, org: str | None = None, query: str | None = None, sort: str | None = None) -> list[dict[str, Any]]:
        if project:
            path = f"/api/0/projects/{quote(org or self.org)}/{quote(project)}/issues/"
        else:
            path = f"/api/0/organizations/{quote(org or self.org)}/issues/"
        return self.request("GET", path, params={"query": query, "sort": sort})

    def issue(self, issue_ref: str) -> dict[str, Any]:
        return self.request("GET", f"/api/0/issues/{quote(issue_ref)}/")

    def issue_events(self, issue_ref: str) -> list[dict[str, Any]]:
        return self.request("GET", f"/api/0/issues/{quote(issue_ref)}/events/")

    def latest_event(self, issue_ref: str) -> dict[str, Any]:
        return self.request("GET", f"/api/0/issues/{quote(issue_ref)}/events/latest/")

    def event(self, event_id: str, project: str, org: str | None = None) -> dict[str, Any]:
        return self.request("GET", f"/api/0/projects/{quote(org or self.org)}/{quote(project)}/events/{quote(event_id)}/")

    def stacktrace(self, issue_ref: str) -> dict[str, Any]:
        event = self.latest_event(issue_ref)
        return {"issue": issue_ref, "event_id": event.get("id"), "stacktrace": event.get("stacktrace", {})}

    def breadcrumbs(self, issue_ref: str) -> dict[str, Any]:
        event = self.latest_event(issue_ref)
        return {"issue": issue_ref, "event_id": event.get("id"), "breadcrumbs": event.get("breadcrumbs", [])}

    def issue_tags(self, issue_ref: str) -> dict[str, Any]:
        issue = self.issue(issue_ref)
        return {"issue_id": issue.get("id"), "shortId": issue.get("shortId"), "tags": issue.get("tags", {})}

    def suspect_commits(self, issue_ref: str) -> list[dict[str, Any]]:
        return self.request("GET", f"/api/0/issues/{quote(issue_ref)}/suspect-commits/")

    def comments(self, issue_ref: str) -> list[dict[str, Any]]:
        return self.request("GET", f"/api/0/issues/{quote(issue_ref)}/comments/")

    def add_comment(self, issue_ref: str, text: str) -> dict[str, Any]:
        return self.request("POST", f"/api/0/issues/{quote(issue_ref)}/comments/", payload={"text": text})

    def activity(self, issue_ref: str) -> list[dict[str, Any]]:
        return self.request("GET", f"/api/0/issues/{quote(issue_ref)}/activity/")

    def assign_issue(self, issue_ref: str, *, team: str | None = None, user: str | None = None) -> dict[str, Any]:
        assigned: dict[str, Any]
        if team:
            assigned = {"type": "team", "slug": team, "name": team}
        elif user:
            assigned = {"type": "user", "email": user, "name": user}
        else:
            raise SentryClientError("team or user is required")
        return self.request("PUT", f"/api/0/issues/{quote(issue_ref)}/", payload={"assignedTo": assigned})

    def resolve_issue(self, issue_ref: str, in_release: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"status": "resolved", "substatus": "resolved"}
        if in_release:
            payload["resolvedInRelease"] = in_release
        return self.request("PUT", f"/api/0/issues/{quote(issue_ref)}/", payload=payload)

    def ignore_issue(self, issue_ref: str, reason: str | None = None) -> dict[str, Any]:
        return self.request("PUT", f"/api/0/issues/{quote(issue_ref)}/", payload={"status": "ignored", "substatus": "until_escalating", "ignoreReason": reason})

    def reopen_issue(self, issue_ref: str) -> dict[str, Any]:
        return self.request("PUT", f"/api/0/issues/{quote(issue_ref)}/", payload={"status": "unresolved", "substatus": "ongoing"})

    def releases(self, *, project: str | None = None, org: str | None = None) -> list[dict[str, Any]]:
        return self.request("GET", f"/api/0/organizations/{quote(org or self.org)}/releases/", params={"project": project})

    def release(self, version: str, *, project: str | None = None, org: str | None = None) -> dict[str, Any]:
        return self.request("GET", f"/api/0/organizations/{quote(org or self.org)}/releases/{quote(version)}/", params={"project": project})

    def release_commits(self, version: str, *, project: str | None = None, org: str | None = None) -> list[dict[str, Any]]:
        return self.release(version, project=project, org=org).get("commits", [])

    def ownership(self, project: str, org: str | None = None) -> list[dict[str, Any]]:
        return self.request("GET", f"/api/0/projects/{quote(org or self.org)}/{quote(project)}/ownership/")

    def clone_state(self) -> dict[str, Any]:
        return self.request("GET", "/api/_clone/state")

    def clone_mutations(self) -> list[dict[str, Any]]:
        return self.request("GET", "/api/_clone/mutations")


class SentryAdminClient(SentryClient):
    def __init__(self, base_url: str | None = None, token: str | None = None, org: str | None = None):
        super().__init__(base_url=base_url, token=token or _admin_token(), org=org)


def quote(value: str) -> str:
    return urllib.parse.quote(str(value), safe="")


def _error_message(body: str) -> str | None:
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return body or None
    for key in ("detail", "message", "error"):
        if data.get(key):
            return str(data[key])
    return None

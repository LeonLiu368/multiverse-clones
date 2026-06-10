from __future__ import annotations

import errno
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable

from .config import Config
from .errors import (
    AuthError,
    BackendUnavailableError,
    ConflictError,
    NotFoundError,
    UnsupportedCommandError,
    WorldIssuesError,
    redact,
)
from .manifest import issue_mapping, read_manifest, resolve_issue_ref
from .models import issue_url, now_iso


def _list_from_response(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("results", "data", "items", "issues", "comments", "links", "states", "labels"):
            value = data.get(key)
            if isinstance(value, list):
                return value
    return []


def _first_present(data: dict[str, Any], names: tuple[str, ...], default: Any = None) -> Any:
    for name in names:
        if name in data and data[name] is not None:
            return data[name]
    return default


def _slug(value: str) -> str:
    return "-".join(part for part in "".join(ch.lower() if ch.isalnum() else "-" for ch in value).split("-") if part)


class PlaneHttpClient:
    """Small real Plane adapter.

    Endpoint paths are intentionally centralized here so higher layers can remain stable if Plane's
    API shape needs final adjustment for a deployed instance.
    """

    def __init__(self, config: Config):
        config.require_plane()
        self.config = config
        self.base_url = (config.base_url or "").rstrip("/")
        self.workspace = config.workspace or ""
        self.api_prefix = "/api/v1"
        self._project_cache: dict[str, dict[str, Any]] = {}
        self._states_cache: list[dict[str, Any]] | None = None
        self._labels_cache: list[dict[str, Any]] | None = None
        self._members_cache: list[dict[str, Any]] | None = None
        self._cycles_cache: list[dict[str, Any]] | None = None
        self._modules_cache: list[dict[str, Any]] | None = None

    def _api_path(self, path: str) -> str:
        return self.api_prefix + path

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
        retry: int = 1,
    ) -> Any:
        url = self.base_url + path
        if params:
            query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
            if query:
                url += "?" + query
        data = None
        headers = {"X-API-Key": self.config.api_key or "", "Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                body = response.read().decode("utf-8")
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            message = redact(body) or exc.reason
            if exc.code in (500, 502, 503, 504, 429) and method == "GET" and retry:
                time.sleep(0.2)
                return self._request(method, path, params=params, payload=payload, retry=retry - 1)
            if exc.code == 401:
                raise AuthError("Plane authentication failed")
            if exc.code == 404:
                raise NotFoundError(f"Plane resource not found: {method} {path}")
            if exc.code == 409:
                raise ConflictError(f"Plane conflict: {message}")
            if exc.code == 429:
                raise BackendUnavailableError(f"Plane rate limit exceeded: {message}")
            if exc.code >= 500:
                raise BackendUnavailableError(f"Plane backend unavailable: {message}")
            raise WorldIssuesError(f"Plane request failed with HTTP {exc.code}: {message}")
        except urllib.error.URLError as exc:
            raise BackendUnavailableError(f"Plane network failure: {redact(exc.reason)}") from exc

    def paginate(self, path: str, *, params: dict[str, Any] | None = None) -> Iterable[dict[str, Any]]:
        cursor = (params or {}).get("cursor")
        while True:
            page_params = dict(params or {})
            if cursor:
                page_params["cursor"] = cursor
            data = self._request("GET", path, params=page_params)
            if isinstance(data, dict) and "results" in data:
                for item in data["results"]:
                    yield item
                if data.get("next_page_results") is False:
                    break
                cursor = data.get("next_cursor") or data.get("next")
                if not cursor:
                    break
            elif isinstance(data, list):
                yield from data
                break
            else:
                break

    def projects(self) -> list[dict[str, Any]]:
        path = self._api_path(f"/workspaces/{self.workspace}/projects/")
        return list(self.paginate(path))

    def project_list(self) -> list[dict[str, Any]]:
        return [self._normalize_project(project) for project in self.projects()]

    def project_view(self, project: str) -> dict[str, Any]:
        found = self._resolve_project(project)
        result = self._normalize_project(found)
        result["members"] = self.project_members(result["id"])
        return result

    def project_members(self, project_id: str | None = None) -> list[dict[str, Any]]:
        project_id = project_id or self._default_project()["id"]
        if project_id == self._default_project()["id"] and self._members_cache is not None:
            return self._members_cache
        path = self._api_path(f"/workspaces/{self.workspace}/projects/{project_id}/members/")
        members = [self._normalize_user(item) for item in self.paginate(path)]
        if project_id == self._default_project()["id"]:
            self._members_cache = members
        return members

    def current_user(self) -> dict[str, Any]:
        for path in (self._api_path("/users/me/"), "/api/users/me/", "/api/me/"):
            try:
                return self._normalize_user(self._request("GET", path))
            except NotFoundError:
                continue
        raise UnsupportedCommandError("Plane current user endpoint is unavailable")

    def list_states(self) -> list[dict[str, Any]]:
        if self._states_cache is not None:
            return self._states_cache
        project = self._default_project()
        path = self._api_path(f"/workspaces/{self.workspace}/projects/{project['id']}/states/")
        self._states_cache = [self._normalize_state(item) for item in self.paginate(path)]
        return self._states_cache

    def list_labels(self) -> list[dict[str, Any]]:
        if self._labels_cache is not None:
            return self._labels_cache
        project = self._default_project()
        path = self._api_path(f"/workspaces/{self.workspace}/projects/{project['id']}/labels/")
        self._labels_cache = [self._normalize_label(item) for item in self.paginate(path)]
        return self._labels_cache

    def list_cycles(self) -> list[dict[str, Any]]:
        if self._cycles_cache is not None:
            return self._cycles_cache
        project = self._default_project()
        path = self._api_path(f"/workspaces/{self.workspace}/projects/{project['id']}/cycles/")
        self._cycles_cache = [self._normalize_cycle(item) for item in self.paginate(path)]
        return self._cycles_cache

    def current_cycle(self) -> dict[str, Any]:
        cycles = self.list_cycles()
        if not cycles:
            raise NotFoundError("current cycle not found")
        return cycles[0]

    def list_modules(self) -> list[dict[str, Any]]:
        if self._modules_cache is not None:
            return self._modules_cache
        project = self._default_project()
        path = self._api_path(f"/workspaces/{self.workspace}/projects/{project['id']}/modules/")
        self._modules_cache = [self._normalize_module(item) for item in self.paginate(path)]
        return self._modules_cache

    def issue_list(
        self,
        *,
        query: str | None = None,
        filters: dict[str, Any] | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        project = self._default_project()
        params = {"per_page": limit, "cursor": cursor}
        if query:
            params["search"] = query
        for key, value in (filters or {}).items():
            if value in (None, "", []):
                continue
            params[key] = ",".join(value) if isinstance(value, list) else value
        path = self._api_path(f"/workspaces/{self.workspace}/projects/{project['id']}/issues/")
        data = self._request("GET", path, params=params)
        items = _list_from_response(data)
        next_cursor = data.get("next_cursor") or data.get("next") if isinstance(data, dict) else None
        if isinstance(data, dict) and data.get("next_page_results") is False:
            next_cursor = None
        issues = [self._normalize_issue(item, project=project) for item in items]
        if query:
            issues = self._filter_issues_by_query(issues, query)
            next_cursor = None
        return {"results": issues, "next_cursor": next_cursor}

    def issue_mine(self, actor: str, **kwargs: Any) -> dict[str, Any]:
        result = self.issue_list(limit=kwargs.get("limit", 500), query=kwargs.get("query"), filters=kwargs.get("filters"))
        wanted = actor.lower()
        result["results"] = [
            issue
            for issue in result.get("results", [])
            if any(
                wanted in {assignee.get("id", "").lower(), assignee.get("handle", "").lower(), assignee.get("name", "").lower()}
                for assignee in issue.get("assignees", [])
            )
        ]
        result["next_cursor"] = None
        return result

    def get_issue(self, identifier: str) -> dict[str, Any]:
        identifier = self._resolve_issue_api_ref(identifier)
        project = self._default_project()
        path = self._api_path(f"/workspaces/{self.workspace}/projects/{project['id']}/issues/{identifier}/")
        return self._normalize_issue(self._request("GET", path), project=project)

    def create_issue(self, **fields: Any) -> dict[str, Any]:
        project = self._default_project()
        payload = self._issue_payload(fields)
        path = self._api_path(f"/workspaces/{self.workspace}/projects/{project['id']}/issues/")
        return self._normalize_issue(self._request("POST", path, payload=payload), project=project)

    def update_issue(self, identifier: str, **fields: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        before = self.get_issue(identifier)
        identifier = self._resolve_issue_api_ref(identifier)
        project = self._default_project()
        payload = self._issue_payload(fields)
        path = self._api_path(f"/workspaces/{self.workspace}/projects/{project['id']}/issues/{identifier}/")
        after = self._normalize_issue(self._request("PATCH", path, payload=payload), project=project)
        return before, after

    def delete_issue(self, identifier: str) -> tuple[dict[str, Any], None]:
        before = self.get_issue(identifier)
        identifier = self._resolve_issue_api_ref(identifier)
        project = self._default_project()
        path = self._api_path(f"/workspaces/{self.workspace}/projects/{project['id']}/issues/{identifier}/")
        self._request("DELETE", path)
        return before, None

    def list_comments(self, identifier: str) -> list[dict[str, Any]]:
        original_identifier = identifier
        identifier = self._resolve_issue_api_ref(identifier)
        project = self._default_project()
        path = self._api_path(f"/workspaces/{self.workspace}/projects/{project['id']}/issues/{identifier}/comments/")
        return [self._normalize_comment(item, original_identifier) for item in self.paginate(path)]

    def add_comment(self, identifier: str, body: str, *, author: str | None = None) -> dict[str, Any]:
        original_identifier = identifier
        identifier = self._resolve_issue_api_ref(identifier)
        project = self._default_project()
        path = self._api_path(f"/workspaces/{self.workspace}/projects/{project['id']}/issues/{identifier}/comments/")
        return self._normalize_comment(self._request("POST", path, payload={"body": body, "comment_html": body}), original_identifier)

    def list_links(self, identifier: str) -> list[dict[str, Any]]:
        identifier = self._resolve_issue_api_ref(identifier)
        project = self._default_project()
        path = self._api_path(f"/workspaces/{self.workspace}/projects/{project['id']}/issues/{identifier}/links/")
        return [self._normalize_link(item) for item in self.paginate(path)]

    def add_link(self, identifier: str, url: str, title: str) -> dict[str, Any]:
        identifier = self._resolve_issue_api_ref(identifier)
        project = self._default_project()
        path = self._api_path(f"/workspaces/{self.workspace}/projects/{project['id']}/issues/{identifier}/links/")
        return self._normalize_link(self._request("POST", path, payload={"url": self._link_url_payload(url), "title": title}))

    def list_attachments(self, identifier: str) -> list[dict[str, Any]]:
        identifier = self._resolve_issue_api_ref(identifier)
        project = self._default_project()
        path = self._api_path(f"/workspaces/{self.workspace}/projects/{project['id']}/issues/{identifier}/issue-attachments/")
        try:
            return [self._normalize_attachment(item) for item in self.paginate(path)]
        except NotFoundError:
            return []

    def add_attachment(self, identifier: str, name: str, content_type: str, *, size: int = 0) -> dict[str, Any]:
        raise UnsupportedCommandError("Plane attachment upload is not wired; metadata listing is supported when available")

    def list_relations(self, identifier: str) -> list[dict[str, Any]]:
        raise UnsupportedCommandError("Plane relation listing is not wired in v0.5")

    def add_relation(self, identifier: str, relation: str, other: str) -> dict[str, Any]:
        raise UnsupportedCommandError("Plane relation mutation is not wired in v0.5")

    def history_list(self, identifier: str) -> list[dict[str, Any]]:
        raise UnsupportedCommandError("Plane issue history is not wired in v0.5")

    def snapshot(self) -> dict[str, Any]:
        project = self._default_project()
        issues = self.issue_list(limit=500)["results"]
        comments = {issue["identifier"]: self.list_comments(issue["id"]) for issue in issues}
        links = {issue["identifier"]: self.list_links(issue["id"]) for issue in issues}
        attachments = {issue["identifier"]: self.list_attachments(issue["id"]) for issue in issues}
        return {"project": project, "issues": issues, "comments": comments, "links": links, "attachments": attachments, "relations": {}}

    def _default_project(self) -> dict[str, Any]:
        cache_key = (self.config.default_project or "").lower()
        if cache_key in self._project_cache:
            return self._project_cache[cache_key]
        return self._normalize_project(self._resolve_project(self.config.default_project or ""))

    def _resolve_project(self, value: str) -> dict[str, Any]:
        for project in self.projects():
            normalized = self._normalize_project(project)
            if value.lower() in {normalized["id"].lower(), normalized["key"].lower(), normalized["name"].lower()}:
                self._project_cache[value.lower()] = normalized
                self._project_cache[normalized["id"].lower()] = normalized
                self._project_cache[normalized["key"].lower()] = normalized
                return project
        raise NotFoundError(f"project not found: {value}")

    def _resolve_state_id(self, value: str) -> str:
        for state in self.list_states():
            if value.lower() in {state["id"].lower(), state["name"].lower(), state["category"].lower()}:
                return state["id"]
        raise NotFoundError(f"state not found: {value}")

    def _resolve_label_ids(self, values: list[str]) -> list[str]:
        labels = self.list_labels()
        ids = []
        for value in values:
            for label in labels:
                if value.lower() in {label["id"].lower(), label["name"].lower()}:
                    ids.append(label["id"])
                    break
            else:
                raise NotFoundError(f"label not found: {value}")
        return ids

    def _resolve_user_ids(self, values: list[str]) -> list[str]:
        members = self.project_members()
        ids = []
        for value in values:
            for member in members:
                if value.lower() in {member["id"].lower(), member["handle"].lower(), member["name"].lower()}:
                    ids.append(member["id"])
                    break
            else:
                raise NotFoundError(f"user not found: {value}")
        return ids

    def _resolve_cycle_id(self, value: str | None) -> str | None:
        if value is None:
            return None
        for cycle in self.list_cycles():
            if value.lower() in {cycle["id"].lower(), cycle["name"].lower()}:
                return cycle["id"]
        raise NotFoundError(f"cycle not found: {value}")

    def _resolve_module_id(self, value: str | None) -> str | None:
        if value is None:
            return None
        for module in self.list_modules():
            if value.lower() in {module["id"].lower(), module["name"].lower()}:
                return module["id"]
        raise NotFoundError(f"module not found: {value}")

    def _issue_payload(self, fields: dict[str, Any]) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if fields.get("title"):
            payload["name"] = fields["title"]
        if "description" in fields:
            payload["description_html"] = fields.get("description") or ""
            payload["description_stripped"] = fields.get("description") or ""
        if fields.get("priority"):
            payload["priority"] = self._priority_payload(fields["priority"])
        if fields.get("identifier"):
            payload["identifier"] = fields["identifier"]
            if "-" in str(fields["identifier"]):
                payload["sequence_id"] = str(fields["identifier"]).split("-")[-1]
        if fields.get("state"):
            payload["state"] = self._resolve_state_id(fields["state"])
        if "assignees" in fields:
            payload["assignees"] = self._resolve_user_ids(fields["assignees"])
        elif fields.get("assignee"):
            payload["assignees"] = self._resolve_user_ids([fields["assignee"]])
        if "labels" in fields:
            payload["labels"] = self._resolve_label_ids(fields["labels"])
        if "cycle" in fields:
            payload["cycle_id"] = self._resolve_cycle_id(fields["cycle"])
        if "module" in fields:
            payload["module_ids"] = [] if fields["module"] is None else [self._resolve_module_id(fields["module"])]
        return payload

    def _normalize_project(self, data: dict[str, Any]) -> dict[str, Any]:
        key = _first_present(data, ("identifier", "key", "project_key"), "")
        return {
            "id": str(_first_present(data, ("id", "uuid"), key)),
            "key": str(key),
            "name": str(_first_present(data, ("name", "title"), key)),
            "archived": bool(_first_present(data, ("archived", "is_archived"), False)),
        }

    def _normalize_user(self, data: dict[str, Any]) -> dict[str, Any]:
        member = data.get("member") if isinstance(data.get("member"), dict) else data
        handle = str(_first_present(member, ("username", "handle", "email", "id"), ""))
        if "@" in handle and not _first_present(member, ("username", "handle"), ""):
            handle = handle.split("@", 1)[0]
        return {
            "id": str(_first_present(member, ("id", "user_id", "uuid"), "")),
            "name": str(_first_present(member, ("display_name", "name", "first_name", "email"), "")),
            "handle": handle,
        }

    def _normalize_state(self, data: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(_first_present(data, ("id", "uuid"), "")),
            "name": str(_first_present(data, ("name",), "")),
            "category": str(_first_present(data, ("group", "category"), "")).lower(),
        }

    def _normalize_label(self, data: dict[str, Any]) -> dict[str, Any]:
        return {"id": str(_first_present(data, ("id", "uuid"), "")), "name": str(_first_present(data, ("name",), ""))}

    def _normalize_cycle(self, data: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(_first_present(data, ("id", "uuid"), "")),
            "name": str(_first_present(data, ("name",), "")),
            "starts_at": _first_present(data, ("start_date", "starts_at"), None),
            "ends_at": _first_present(data, ("end_date", "ends_at"), None),
        }

    def _normalize_module(self, data: dict[str, Any]) -> dict[str, Any]:
        return {"id": str(_first_present(data, ("id", "uuid"), "")), "name": str(_first_present(data, ("name",), ""))}

    def _normalize_issue(self, data: dict[str, Any], *, project: dict[str, Any] | None = None) -> dict[str, Any]:
        project = project or self._default_project()
        normalized_project = self._normalize_project(project)
        sequence = _first_present(data, ("sequence_id", "number"), None)
        identifier = str(_first_present(data, ("identifier",), ""))
        if not identifier:
            issue_project = data.get("project_detail") if isinstance(data.get("project_detail"), dict) else normalized_project
            key = _first_present(issue_project, ("identifier", "key"), normalized_project["key"])
            identifier = f"{key}-{sequence}" if sequence is not None else str(_first_present(data, ("id",), ""))
        actual_id = str(_first_present(data, ("id", "uuid"), identifier))
        actual_identifier = identifier
        fixture_identifier = self._fixture_identifier(actual_id, actual_identifier)
        identifier = fixture_identifier or identifier
        state_raw = data.get("state_detail") if isinstance(data.get("state_detail"), dict) else data.get("state")
        if isinstance(state_raw, dict):
            state = self._normalize_state(state_raw)
        else:
            state = self._state_from_ref(str(state_raw or ""), str(_first_present(data, ("state_name",), state_raw or "")))
        label_raw = data.get("label_details") or data.get("labels") or []
        labels = [self._normalize_label(item) if isinstance(item, dict) else self._label_from_ref(str(item)) for item in label_raw]
        assignee_raw = data.get("assignee_details") or data.get("assignees") or []
        assignees = [self._normalize_user(item) if isinstance(item, dict) else self._user_from_ref(str(item)) for item in assignee_raw]
        cycle_raw = data.get("cycle_detail") or data.get("cycle")
        if data.get("module_detail"):
            module_raw = data.get("module_detail")
        elif isinstance(data.get("modules"), list):
            module_raw = (data.get("modules") or [None])[0]
        else:
            module_raw = data.get("module")
        return {
            "id": actual_id,
            "actual_identifier": actual_identifier,
            "identifier": identifier,
            "project": normalized_project,
            "title": str(_first_present(data, ("name", "title"), "")),
            "description": str(_first_present(data, ("description_stripped", "description_html", "description"), "")),
            "state": state,
            "priority": self._normalize_priority(_first_present(data, ("priority",), None)),
            "assignees": assignees,
            "labels": labels,
            "cycle": self._normalize_cycle(cycle_raw) if isinstance(cycle_raw, dict) else None,
            "module": self._normalize_module(module_raw) if isinstance(module_raw, dict) else None,
            "links": [],
            "relations": [],
            "comments_count": int(_first_present(data, ("comment_count", "comments_count"), 0) or 0),
            "attachments_count": int(_first_present(data, ("attachment_count", "attachments_count"), 0) or 0),
            "created_at": _first_present(data, ("created_at",), None),
            "updated_at": _first_present(data, ("updated_at",), None),
            "url": issue_url(self.base_url, self.workspace, normalized_project["key"], identifier),
        }

    def _fixture_identifier(self, actual_id: str, actual_identifier: str) -> str | None:
        manifest = read_manifest()
        issues = manifest.get("issues", {}) if isinstance(manifest.get("issues"), dict) else {}
        for fixture_id, mapping in issues.items():
            if not isinstance(mapping, dict):
                continue
            if actual_id and mapping.get("actual_id") == actual_id:
                return fixture_id
            if actual_identifier and mapping.get("actual_identifier") == actual_identifier:
                return fixture_id
        return None

    def _resolve_issue_api_ref(self, value: str) -> str:
        manifest = read_manifest()
        mapping = issue_mapping(manifest, value)
        if mapping:
            return str(mapping.get("actual_id") or mapping.get("actual_identifier") or value)
        issues = manifest.get("issues", {}) if isinstance(manifest.get("issues"), dict) else {}
        for item in issues.values():
            if not isinstance(item, dict):
                continue
            if value in {str(item.get("actual_identifier")), str(item.get("actual_id"))}:
                return str(item.get("actual_id") or value)
        return resolve_issue_ref(value)

    def _priority_payload(self, value: str) -> str:
        mapping = {"critical": "urgent", "none": "none", "urgent": "urgent", "high": "high", "medium": "medium", "low": "low"}
        return mapping.get(str(value).lower(), str(value).lower())

    def _normalize_priority(self, value: Any) -> Any:
        mapping = {"urgent": "critical"}
        return mapping.get(str(value).lower(), value) if value is not None else None

    def _normalize_comment(self, data: dict[str, Any], identifier: str) -> dict[str, Any]:
        return {
            "id": str(_first_present(data, ("id", "uuid"), "")),
            "issue": identifier,
            "author": self._normalize_user(data.get("actor_detail") or data.get("created_by_detail") or data.get("author") or {}),
            "body": str(_first_present(data, ("body", "comment_html", "comment_stripped"), "")),
            "created_at": _first_present(data, ("created_at",), None),
            "updated_at": _first_present(data, ("updated_at",), None),
        }

    def _normalize_link(self, data: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(_first_present(data, ("id", "uuid"), "")),
            "url": str(_first_present(data, ("url",), "")),
            "title": str(_first_present(data, ("title", "metadata"), "")),
        }

    def _link_url_payload(self, url: str) -> str:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme in {"http", "https"}:
            return url
        return "https://ticketvector.local/link/" + urllib.parse.quote(url, safe="")

    def _normalize_attachment(self, data: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(_first_present(data, ("id", "uuid"), "")),
            "name": str(_first_present(data, ("name", "file_name", "asset"), "")),
            "content_type": str(_first_present(data, ("content_type", "mime_type"), "")),
            "size": int(_first_present(data, ("size", "file_size"), 0) or 0),
            "uploaded_at": _first_present(data, ("created_at", "uploaded_at"), None),
        }

    def _state_from_ref(self, state_id: str, fallback: str) -> dict[str, str]:
        if state_id:
            for state in self.list_states():
                if state_id == state["id"]:
                    return state
        return {"id": state_id, "name": fallback, "category": ""}

    def _label_from_ref(self, label_id: str) -> dict[str, str]:
        for label in self.list_labels():
            if label_id == label["id"]:
                return label
        return {"id": label_id, "name": label_id}

    def _user_from_ref(self, user_id: str) -> dict[str, str]:
        for user in self.project_members():
            if user_id == user["id"]:
                return user
        return {"id": user_id, "name": user_id, "handle": user_id}

    def _filter_issues_by_query(self, issues: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
        terms = [term.lower() for term in query.split() if term.strip()]
        if not terms:
            return issues

        def haystack(issue: dict[str, Any]) -> str:
            labels = " ".join(label.get("name", "") for label in issue.get("labels", []))
            assignees = " ".join(user.get("handle", "") for user in issue.get("assignees", []))
            module = issue.get("module", {}) or {}
            cycle = issue.get("cycle", {}) or {}
            return " ".join(
                [
                    issue.get("identifier", ""),
                    issue.get("title", ""),
                    issue.get("description", ""),
                    issue.get("priority", ""),
                    labels,
                    assignees,
                    module.get("name", ""),
                    cycle.get("name", ""),
                ]
            ).lower()

        return [issue for issue in issues if all(term in haystack(issue) for term in terms)]


class FakePlaneBackend:
    def __init__(self, config: Config | None = None, *, state_file: str | Path | None = None):
        self.config = config
        self.state_file = Path(state_file or (config.state_file if config else ".ticketvector/state.json"))
        self._suspend_save = False
        if self.state_file.exists():
            self._load()
        else:
            self.reset()

    def _load(self) -> None:
        data = json.loads(self.state_file.read_text(encoding="utf-8"))
        self.base_url = data.get("base_url", "https://plane.local")
        self.workspace = data.get("workspace", "acme")
        self.project = data["project"]
        self.users = data["users"]
        self.states = data["states"]
        self.labels = data["labels"]
        self.cycles = data["cycles"]
        self.modules = data["modules"]
        self.comments = data.get("comments", {})
        self.links = data.get("links", {})
        self.attachments = data.get("attachments", {})
        self.relations = data.get("relations", {})
        self.history = data.get("history", {})
        self.issues = data.get("issues", [])

    def _save(self) -> None:
        if self._suspend_save:
            return
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        body = json.dumps(self.snapshot(), indent=2, sort_keys=True) + "\n"
        tmp = self.state_file.with_name(f".{self.state_file.name}.tmp")
        tmp.write_text(body, encoding="utf-8")
        try:
            tmp.replace(self.state_file)
        except OSError as exc:
            if exc.errno not in {errno.EBUSY, errno.EXDEV}:
                raise
            # Docker single-file bind mounts can reject atomic rename over the
            # mount target. Fall back to rewriting the file in place so task
            # fixtures mounted as files still persist state transitions.
            self.state_file.write_text(body, encoding="utf-8")
            tmp.unlink(missing_ok=True)

    def reset(self) -> None:
        self._suspend_save = True
        self.base_url = "https://plane.local"
        self.workspace = "acme"
        self.project = {"id": "proj-pay", "key": "PAY", "name": "Payments", "archived": False}
        self.users = [
            {"id": "user-agent", "name": "Agent User", "handle": "agent"},
            {"id": "user-owen", "name": "Owen", "handle": "owen"},
            {"id": "user-leon", "name": "Leon", "handle": "leon"},
            {"id": "user-joshua", "name": "Joshua", "handle": "joshua"},
            {"id": "user-priya", "name": "Priya", "handle": "priya"},
        ]
        self.states = [
            {"id": "state-backlog", "name": "Backlog", "category": "backlog"},
            {"id": "state-todo", "name": "Todo", "category": "unstarted"},
            {"id": "state-progress", "name": "In Progress", "category": "started"},
            {"id": "state-review", "name": "In Review", "category": "started"},
            {"id": "state-blocked", "name": "Blocked", "category": "started"},
            {"id": "state-done", "name": "Done", "category": "completed"},
            {"id": "state-canceled", "name": "Canceled", "category": "cancelled"},
        ]
        self.labels = [
            self._label(name)
            for name in [
                "backend",
                "frontend",
                "infra",
                "database",
                "flaky-test",
                "customer-report",
                "regression",
                "security",
                "observability",
            ]
        ]
        self.cycles = [
            {
                "id": "cycle-a",
                "name": "Sprint 2026-06-A",
                "starts_at": "2026-06-01",
                "ends_at": "2026-06-14",
            },
            {
                "id": "cycle-b",
                "name": "Sprint 2026-06-B",
                "starts_at": "2026-06-15",
                "ends_at": "2026-06-28",
            },
        ]
        self.modules = [
            {"id": "module-checkout", "name": "Checkout Reliability"},
            {"id": "module-billing", "name": "Billing Portal"},
            {"id": "module-webhook", "name": "Webhook Delivery"},
            {"id": "module-auth", "name": "Auth Hardening"},
        ]
        self.comments: dict[str, list[dict[str, Any]]] = {}
        self.links: dict[str, list[dict[str, Any]]] = {}
        self.attachments: dict[str, list[dict[str, Any]]] = {}
        self.relations: dict[str, list[dict[str, Any]]] = {}
        self.history: dict[str, list[dict[str, Any]]] = {}
        self.issues = []
        self._seed_issues()
        self._suspend_save = False
        self._save()

    def _label(self, name: str) -> dict[str, str]:
        return {"id": f"label-{name}", "name": name}

    def _user(self, handle: str) -> dict[str, str]:
        for user in self.users:
            if user["handle"] == handle or user["id"] == handle or user["name"].lower() == handle.lower():
                return deepcopy(user)
        raise NotFoundError(f"user not found: {handle}")

    def _state(self, name: str) -> dict[str, str]:
        for state in self.states:
            if state["id"] == name or state["name"].lower() == name.lower() or state["category"] == name:
                return deepcopy(state)
        raise NotFoundError(f"state not found: {name}")

    def _labels(self, names: list[str]) -> list[dict[str, str]]:
        wanted = set(names)
        return [deepcopy(label) for label in self.labels if label["name"] in wanted]

    def _cycle(self, name: str | None) -> dict[str, str] | None:
        if not name:
            return None
        for cycle in self.cycles:
            if cycle["id"] == name or cycle["name"].lower() == name.lower():
                return deepcopy(cycle)
        raise NotFoundError(f"cycle not found: {name}")

    def _module(self, name: str | None) -> dict[str, str] | None:
        if not name:
            return None
        for module in self.modules:
            if module["id"] == name or module["name"].lower() == name.lower():
                return deepcopy(module)
        raise NotFoundError(f"module not found: {name}")

    def _make_issue(
        self,
        number: int,
        title: str,
        *,
        description: str,
        state: str = "Todo",
        priority: str = "medium",
        assignees: list[str] | None = None,
        labels: list[str] | None = None,
        cycle: str | None = "Sprint 2026-06-A",
        module: str | None = None,
    ) -> dict[str, Any]:
        identifier = f"PAY-{number}"
        issue = {
            "id": f"issue-{identifier.lower()}",
            "identifier": identifier,
            "project": deepcopy(self.project),
            "title": title,
            "description": description,
            "state": self._state(state),
            "priority": priority,
            "assignees": [self._user(handle) for handle in (assignees or [])],
            "labels": self._labels(labels or []),
            "cycle": self._cycle(cycle),
            "module": self._module(module),
            "links": [],
            "relations": [],
            "comments_count": 0,
            "attachments_count": 0,
            "created_at": f"2026-06-{number - 100:02d}T09:00:00Z",
            "updated_at": f"2026-06-{number - 100:02d}T10:00:00Z",
            "url": issue_url(self.base_url, self.workspace, self.project["key"], identifier),
        }
        return issue

    def _seed_issues(self) -> None:
        specs = [
            (101, "Critical bug: webhook retry worker drops Stripe events after Redis reconnect", "Redis reconnects leave the Stripe retry worker with a stale stream cursor.", "Todo", "critical", [], ["backend", "regression"], "Webhook Delivery"),
            (102, "Add regression test for duplicate webhook delivery", "Cover duplicate event delivery and assert idempotent processing.", "Backlog", "high", ["leon"], ["backend", "regression"], "Webhook Delivery"),
            (103, "Investigate checkout 500s after deploy 2026-06-02", "Checkout errors spiked after the Tuesday deploy.", "In Progress", "high", ["owen"], ["backend", "customer-report"], "Checkout Reliability"),
            (104, "Billing portal shows stale invoice status", "The portal can show paid invoices as open for several minutes.", "Todo", "medium", ["joshua"], ["frontend"], "Billing Portal"),
            (105, "Refactor payment provider adapter error mapping", "Normalize provider errors for cleaner retry decisions.", "Backlog", "medium", [], ["backend"], "Checkout Reliability"),
            (106, "Add Grafana dashboard link to webhook delivery runbook", "Runbook should link to retry queue age and worker error panels.", "Todo", "low", ["agent"], ["observability"], "Webhook Delivery"),
            (107, "Customer report: ACH payment stuck in pending", "Priya reported an ACH payment that stayed pending after settlement.", "Blocked", "high", ["priya"], ["customer-report", "backend"], "Billing Portal"),
            (108, "Fix flaky Playwright checkout test", "Checkout e2e intermittently times out waiting for confirmation.", "Todo", "medium", ["agent"], ["flaky-test", "frontend"], "Checkout Reliability"),
            (109, "Add idempotency key validation to refund endpoint", "Reject malformed idempotency keys before refund creation.", "Backlog", "high", [], ["backend", "security"], "Checkout Reliability"),
            (110, "Security review: redact payment tokens in logs", "Audit payment logs and remove token-like fields.", "Todo", "critical", ["owen"], ["security", "backend"], "Auth Hardening"),
            (111, "Migrate webhook event table index", "Add composite index for provider event lookup.", "In Review", "high", ["leon"], ["database", "backend"], "Webhook Delivery"),
            (112, "Add alert for retry queue age", "Alert when retry queue age exceeds ten minutes.", "Backlog", "medium", [], ["observability", "backend"], "Webhook Delivery"),
            (113, "Duplicate of PAY-101 from support intake", "Support intake surfaced the same Redis reconnect bug.", "Todo", "medium", [], ["customer-report", "regression"], "Webhook Delivery"),
            (114, "Follow-up: document Stripe outage handling", "Document operational steps for Stripe degraded availability.", "Backlog", "low", [], ["observability"], "Webhook Delivery"),
        ]
        for number, title, desc, state, priority, assignees, labels, module in specs:
            self.issues.append(
                self._make_issue(
                    number,
                    title,
                    description=desc,
                    state=state,
                    priority=priority,
                    assignees=assignees,
                    labels=labels,
                    module=module,
                )
            )
        self._add_relation("PAY-101", "blocks", "PAY-102")
        self._add_relation("PAY-101", "blocks", "PAY-112")
        self._add_relation("PAY-113", "duplicates", "PAY-101")
        self._add_relation("PAY-103", "relates-to", "PAY-111")
        self._add_relation("PAY-110", "blocks", "PAY-106")
        for author, body in [
            ("priya", "Support has three merchants reporting missing Stripe webhooks after Redis failover."),
            ("owen", "I saw retry queue depth recover, but event offsets did not advance for older shards."),
            ("leon", "The worker logs show reconnect followed by an empty poll loop."),
            ("joshua", "Customer-facing impact is delayed fulfillment for paid orders."),
        ]:
            self.add_comment("PAY-101", body, author=author)
        self.add_comment("PAY-107", "Customer is blocked on month-end reconciliation.", author="priya")
        self.add_link("PAY-101", "https://github.com/acme/payments/pull/000", "PR placeholder")
        self.add_link("PAY-101", "https://runbooks.acme.local/webhook-delivery", "Webhook runbook")
        self.add_attachment("PAY-101", "redis-reconnect-worker.log", "text/plain", size=18420)
        self.add_link("PAY-108", "artifact://playwright/checkout-flake", "Playwright checkout artifact")

    def _touch(self, issue: dict[str, Any]) -> None:
        issue["updated_at"] = now_iso()

    def current_user(self) -> dict[str, str]:
        actor = self.config.actor if self.config else "agent"
        return self._user(actor)

    def project_list(self) -> list[dict[str, Any]]:
        return [deepcopy(self.project)]

    def project_view(self, project: str) -> dict[str, Any]:
        if project.lower() in {self.project["id"], self.project["key"].lower(), self.project["name"].lower()}:
            result = deepcopy(self.project)
            result["members"] = deepcopy(self.users)
            return result
        raise NotFoundError(f"project not found: {project}")

    def create_project(self, name: str, key: str) -> dict[str, Any]:
        if key.upper() == self.project["key"]:
            raise ConflictError(f"project already exists: {key}")
        return {"id": f"proj-{key.lower()}", "key": key.upper(), "name": name, "archived": False}

    def list_states(self) -> list[dict[str, Any]]:
        return deepcopy(self.states)

    def create_state(self, name: str, category: str) -> dict[str, Any]:
        state = {"id": f"state-{name.lower().replace(' ', '-')}", "name": name, "category": category}
        self.states.append(state)
        self._save()
        return deepcopy(state)

    def list_labels(self) -> list[dict[str, Any]]:
        return deepcopy(self.labels)

    def create_label(self, name: str) -> dict[str, Any]:
        label = self._label(name)
        self.labels.append(label)
        self._save()
        return deepcopy(label)

    def list_cycles(self) -> list[dict[str, Any]]:
        return deepcopy(self.cycles)

    def current_cycle(self) -> dict[str, Any]:
        return deepcopy(self.cycles[0])

    def list_modules(self) -> list[dict[str, Any]]:
        return deepcopy(self.modules)

    def issue_list(
        self,
        *,
        query: str | None = None,
        filters: dict[str, Any] | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        filters = filters or {}
        items = [deepcopy(issue) for issue in self.issues]
        if query:
            needle = query.lower()
            tokens = [token for token in _slug(query).split("-") if token]
            items = [
                issue
                for issue in items
                if needle in issue["title"].lower()
                or needle in issue["description"].lower()
                or needle in issue["identifier"].lower()
                or all(
                    token
                    in f"{issue['identifier']} {issue['title']} {issue['description']} {' '.join(label['name'] for label in issue.get('labels', []))}".lower()
                    for token in tokens
                )
            ]
        items = [issue for issue in items if self._matches(issue, filters)]
        items.sort(key=lambda issue: issue["identifier"])
        start = int(cursor or 0)
        end = start + limit
        page = items[start:end]
        next_cursor = str(end) if end < len(items) else None
        return {"results": page, "next_cursor": next_cursor}

    def _matches(self, issue: dict[str, Any], filters: dict[str, Any]) -> bool:
        for key, expected in filters.items():
            if expected in (None, "", []):
                continue
            values = expected if isinstance(expected, list) else [expected]
            values_lower = {str(value).lower() for value in values}
            if key == "assignee":
                handles = {user["handle"].lower() for user in issue.get("assignees", [])}
                if "me" in values_lower:
                    actor = self.config.actor if self.config else "agent"
                    values_lower.remove("me")
                    values_lower.add(actor.lower())
                if not handles.intersection(values_lower):
                    return False
            elif key == "state":
                if issue["state"]["name"].lower() not in values_lower:
                    return False
            elif key == "state_ne":
                if issue["state"]["name"].lower() in values_lower:
                    return False
            elif key == "state_category":
                if issue["state"]["category"].lower() not in values_lower:
                    return False
            elif key == "label":
                labels = {label["name"].lower() for label in issue.get("labels", [])}
                if not labels.intersection(values_lower):
                    return False
            elif key == "priority":
                if issue.get("priority", "").lower() not in values_lower:
                    return False
            elif key == "project":
                if issue["project"]["key"].lower() not in values_lower and issue["project"]["name"].lower() not in values_lower:
                    return False
            elif key == "cycle_empty":
                if bool(issue.get("cycle")) is not bool(expected):
                    return False
            elif key == "search":
                needle = str(expected).lower()
                if needle not in issue["title"].lower() and needle not in issue["description"].lower():
                    return False
            elif key == "module":
                module = issue.get("module")
                if not module or module["name"].lower() not in values_lower:
                    return False
        return True

    def issue_mine(self, actor: str, **kwargs: Any) -> dict[str, Any]:
        return self.issue_list(filters={"assignee": actor, "state_ne": "Done"}, **kwargs)

    def get_issue(self, identifier: str) -> dict[str, Any]:
        for issue in self.issues:
            if issue["identifier"].lower() == identifier.lower() or issue["id"] == identifier:
                result = deepcopy(issue)
                result["comments_count"] = len(self.comments.get(issue["identifier"], []))
                result["attachments_count"] = len(self.attachments.get(issue["identifier"], []))
                result["links"] = deepcopy(self.links.get(issue["identifier"], []))
                result["relations"] = deepcopy(self.relations.get(issue["identifier"], []))
                return result
        raise NotFoundError(f"issue not found: {identifier}")

    def _issue_ref(self, identifier: str) -> dict[str, Any]:
        for issue in self.issues:
            if issue["identifier"].lower() == identifier.lower() or issue["id"] == identifier:
                return issue
        raise NotFoundError(f"issue not found: {identifier}")

    def create_issue(self, **fields: Any) -> dict[str, Any]:
        if fields.get("identifier") and "-" in str(fields["identifier"]):
            number = int(str(fields["identifier"]).split("-")[-1])
        else:
            number = max(int(issue["identifier"].split("-")[1]) for issue in self.issues) + 1
        if any(issue["identifier"] == f"PAY-{number}" for issue in self.issues):
            raise ConflictError(f"issue already exists: PAY-{number}")
        issue = self._make_issue(
            number,
            fields["title"],
            description=fields.get("description", ""),
            state=fields.get("state", "Todo"),
            priority=fields.get("priority", "medium"),
            assignees=[fields["assignee"]] if fields.get("assignee") else [],
            labels=fields.get("labels", []),
            module=fields.get("module"),
            cycle=fields.get("cycle") or "Sprint 2026-06-A",
        )
        self.issues.append(issue)
        self._save()
        return deepcopy(issue)

    def update_issue(self, identifier: str, **fields: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        issue = self._issue_ref(identifier)
        before = deepcopy(issue)
        if "title" in fields and fields["title"]:
            issue["title"] = fields["title"]
        if "description" in fields and fields["description"] is not None:
            issue["description"] = fields["description"]
        if "priority" in fields and fields["priority"]:
            issue["priority"] = fields["priority"]
        if "state" in fields and fields["state"]:
            issue["state"] = self._state(fields["state"])
        if "assignees" in fields:
            issue["assignees"] = [self._user(user) for user in fields["assignees"]]
        if "labels" in fields:
            issue["labels"] = self._labels(fields["labels"])
        if "cycle" in fields:
            issue["cycle"] = self._cycle(fields["cycle"])
        if "module" in fields:
            issue["module"] = self._module(fields["module"])
        self._touch(issue)
        self.history.setdefault(issue["identifier"], []).append(
            {"at": now_iso(), "action": "issue.update", "before": before, "after": deepcopy(issue)}
        )
        self._save()
        return before, deepcopy(issue)

    def delete_issue(self, identifier: str) -> tuple[dict[str, Any], None]:
        issue = self._issue_ref(identifier)
        before = deepcopy(issue)
        self.issues = [item for item in self.issues if item["identifier"] != issue["identifier"]]
        self._save()
        return before, None

    def add_comment(self, identifier: str, body: str, *, author: str | None = None) -> dict[str, Any]:
        issue = self._issue_ref(identifier)
        comment = {
            "id": f"comment-{identifier.lower()}-{len(self.comments.get(issue['identifier'], [])) + 1}",
            "issue": issue["identifier"],
            "author": self._user(author or (self.config.actor if self.config else "agent")),
            "body": body,
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
        self.comments.setdefault(issue["identifier"], []).append(comment)
        self._touch(issue)
        self._save()
        return deepcopy(comment)

    def list_comments(self, identifier: str) -> list[dict[str, Any]]:
        issue = self._issue_ref(identifier)
        return deepcopy(self.comments.get(issue["identifier"], []))

    def add_link(self, identifier: str, url: str, title: str) -> dict[str, Any]:
        issue = self._issue_ref(identifier)
        link = {
            "id": f"link-{identifier.lower()}-{len(self.links.get(issue['identifier'], [])) + 1}",
            "url": url,
            "title": title,
        }
        self.links.setdefault(issue["identifier"], []).append(link)
        self._touch(issue)
        self._save()
        return deepcopy(link)

    def list_links(self, identifier: str) -> list[dict[str, Any]]:
        issue = self._issue_ref(identifier)
        return deepcopy(self.links.get(issue["identifier"], []))

    def add_attachment(self, identifier: str, name: str, content_type: str, *, size: int = 0) -> dict[str, Any]:
        issue = self._issue_ref(identifier)
        attachment = {
            "id": f"attachment-{identifier.lower()}-{len(self.attachments.get(issue['identifier'], [])) + 1}",
            "name": name,
            "content_type": content_type,
            "size": size,
            "uploaded_at": now_iso(),
        }
        self.attachments.setdefault(issue["identifier"], []).append(attachment)
        self._touch(issue)
        self._save()
        return deepcopy(attachment)

    def list_attachments(self, identifier: str) -> list[dict[str, Any]]:
        issue = self._issue_ref(identifier)
        return deepcopy(self.attachments.get(issue["identifier"], []))

    def _add_relation(self, identifier: str, relation: str, other: str) -> dict[str, Any]:
        item = {
            "id": f"relation-{identifier.lower()}-{len(self.relations.get(identifier, [])) + 1}",
            "type": relation,
            "issue": identifier,
            "related_issue": other,
        }
        self.relations.setdefault(identifier, []).append(item)
        return item

    def add_relation(self, identifier: str, relation: str, other: str) -> dict[str, Any]:
        self._issue_ref(identifier)
        self._issue_ref(other)
        item = deepcopy(self._add_relation(identifier, relation, other))
        self._save()
        return item

    def list_relations(self, identifier: str) -> list[dict[str, Any]]:
        issue = self._issue_ref(identifier)
        return deepcopy(self.relations.get(issue["identifier"], []))

    def history_list(self, identifier: str) -> list[dict[str, Any]]:
        issue = self._issue_ref(identifier)
        return deepcopy(self.history.get(issue["identifier"], []))

    def snapshot(self) -> dict[str, Any]:
        return {
            "base_url": self.base_url,
            "workspace": self.workspace,
            "project": deepcopy(self.project),
            "users": deepcopy(self.users),
            "states": deepcopy(self.states),
            "labels": deepcopy(self.labels),
            "cycles": deepcopy(self.cycles),
            "modules": deepcopy(self.modules),
            "issues": deepcopy(self.issues),
            "comments": deepcopy(self.comments),
            "links": deepcopy(self.links),
            "attachments": deepcopy(self.attachments),
            "relations": deepcopy(self.relations),
            "history": deepcopy(self.history),
        }


def backend_for(config: Config, *, force_backend: str | None = None) -> FakePlaneBackend | PlaneHttpClient | RemoteTicketBackend:
    backend = force_backend or config.backend
    if backend == "fake":
        return FakePlaneBackend(config, state_file=config.state_file)
    if backend == "remote":
        return RemoteTicketBackend(config)
    if backend == "plane":
        return PlaneHttpClient(config)
    raise UnsupportedCommandError(f"unsupported backend: {backend}")


class RemoteTicketBackend:
    def __init__(self, config: Config):
        self.config = config
        self.base_url = (config.base_url or "http://127.0.0.1:8765").rstrip("/")

    def _rpc(self, method: str, *args: Any, **kwargs: Any) -> Any:
        payload = json.dumps({"method": method, "args": args, "kwargs": kwargs}).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + "/rpc",
            data=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise BackendUnavailableError(f"ticketvector service unavailable: {redact(exc.reason)}") from exc
        if data.get("ok"):
            return data.get("result")
        error_type = data.get("error_type")
        message = data.get("error") or "ticketvector service request failed"
        if error_type == "NotFoundError":
            raise NotFoundError(message)
        if error_type == "ConflictError":
            raise ConflictError(message)
        if error_type == "UnsupportedCommandError":
            raise UnsupportedCommandError(message)
        if error_type == "AuthError":
            raise AuthError(message)
        if error_type == "BackendUnavailableError":
            raise BackendUnavailableError(message)
        raise WorldIssuesError(message)

    def current_user(self) -> dict[str, Any]:
        return self._rpc("current_user")

    def project_list(self) -> list[dict[str, Any]]:
        return self._rpc("project_list")

    def project_view(self, project: str) -> dict[str, Any]:
        return self._rpc("project_view", project)

    def create_project(self, name: str, key: str) -> dict[str, Any]:
        return self._rpc("create_project", name, key)

    def list_states(self) -> list[dict[str, Any]]:
        return self._rpc("list_states")

    def create_state(self, name: str, category: str) -> dict[str, Any]:
        return self._rpc("create_state", name, category)

    def list_labels(self) -> list[dict[str, Any]]:
        return self._rpc("list_labels")

    def create_label(self, name: str) -> dict[str, Any]:
        return self._rpc("create_label", name)

    def list_cycles(self) -> list[dict[str, Any]]:
        return self._rpc("list_cycles")

    def current_cycle(self) -> dict[str, Any]:
        return self._rpc("current_cycle")

    def list_modules(self) -> list[dict[str, Any]]:
        return self._rpc("list_modules")

    def issue_list(
        self,
        *,
        query: str | None = None,
        filters: dict[str, Any] | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        return self._rpc("issue_list", query=query, filters=filters, limit=limit, cursor=cursor)

    def issue_mine(self, actor: str, **kwargs: Any) -> dict[str, Any]:
        return self._rpc("issue_mine", actor, **kwargs)

    def get_issue(self, identifier: str) -> dict[str, Any]:
        return self._rpc("get_issue", identifier)

    def create_issue(self, **fields: Any) -> dict[str, Any]:
        return self._rpc("create_issue", **fields)

    def update_issue(self, identifier: str, **fields: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        return tuple(self._rpc("update_issue", identifier, **fields))

    def delete_issue(self, identifier: str) -> tuple[dict[str, Any], None]:
        before, after = self._rpc("delete_issue", identifier)
        return before, after

    def add_comment(self, identifier: str, body: str, *, author: str | None = None) -> dict[str, Any]:
        return self._rpc("add_comment", identifier, body, author=author)

    def list_comments(self, identifier: str) -> list[dict[str, Any]]:
        return self._rpc("list_comments", identifier)

    def add_link(self, identifier: str, url: str, title: str) -> dict[str, Any]:
        return self._rpc("add_link", identifier, url, title)

    def list_links(self, identifier: str) -> list[dict[str, Any]]:
        return self._rpc("list_links", identifier)

    def add_attachment(self, identifier: str, name: str, content_type: str, *, size: int = 0) -> dict[str, Any]:
        return self._rpc("add_attachment", identifier, name, content_type, size=size)

    def list_attachments(self, identifier: str) -> list[dict[str, Any]]:
        return self._rpc("list_attachments", identifier)

    def add_relation(self, identifier: str, relation: str, other: str) -> dict[str, Any]:
        return self._rpc("add_relation", identifier, relation, other)

    def list_relations(self, identifier: str) -> list[dict[str, Any]]:
        return self._rpc("list_relations", identifier)

    def history_list(self, identifier: str) -> list[dict[str, Any]]:
        return self._rpc("history_list", identifier)

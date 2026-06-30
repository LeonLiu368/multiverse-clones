from __future__ import annotations

import json
import os
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from . import clone_admin, comments, events, issues, organizations, ownership, projects, releases
from .auth import check_admin_authorization, check_authorization, sentry_error
from .state import SentryStore, StateError


def make_handler(store: SentryStore) -> type[BaseHTTPRequestHandler]:
    class SentryHandler(BaseHTTPRequestHandler):
        server_version = "SentryClone"
        sys_version = ""

        def log_message(self, format: str, *args: Any) -> None:
            return

        def do_GET(self) -> None:
            self._dispatch("GET")

        def do_POST(self) -> None:
            self._dispatch("POST")

        def do_PUT(self) -> None:
            self._dispatch("PUT")

        def _dispatch(self, method: str) -> None:
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            params = urllib.parse.parse_qs(parsed.query)

            if path.startswith("/api/_clone"):
                auth = check_admin_authorization(self.headers.get("Authorization"))
                if not auth.ok:
                    self._send(auth.status, auth.payload)
                    return
            elif path != "/api/healthz":
                auth = check_authorization(self.headers.get("Authorization"))
                if not auth.ok:
                    self._send(auth.status, auth.payload)
                    return

            try:
                if method == "GET":
                    status, payload = self._handle_get(path, params)
                elif method == "POST":
                    status, payload = self._handle_post(path)
                elif method == "PUT":
                    status, payload = self._handle_put(path)
                else:
                    status, payload = 405, sentry_error("Method not allowed", 405)
            except KeyError as exc:
                status, payload = 404, sentry_error(str(exc).strip("'") or "Not found", 404)
            except ValueError as exc:
                status, payload = 400, sentry_error(str(exc), 400)
            except Exception as exc:
                status, payload = 500, sentry_error(f"Sentry-clone internal error: {type(exc).__name__}", 500)
            self._send(status, payload)

        def _handle_get(self, path: str, params: dict[str, list[str]]) -> tuple[int, Any]:
            parts = _parts(path)
            if path == "/api/healthz":
                return 200, {"ok": True, "version": "sentry-clone-local"}
            if path == "/api/0/user":
                return 200, organizations.current_user(store)
            if path == "/api/0/organizations":
                return 200, organizations.list_organizations(store)
            if len(parts) == 5 and parts[:3] == ["api", "0", "organizations"] and parts[4] == "projects":
                return 200, projects.list_projects(store, parts[3])
            if len(parts) == 5 and parts[:3] == ["api", "0", "projects"]:
                item = projects.get_project(store, parts[3], parts[4])
                return _found(item)
            if len(parts) == 6 and parts[:3] == ["api", "0", "projects"] and parts[5] == "issues":
                return 200, issues.list_project_issues(store, parts[3], parts[4], _param(params, "query"), _param(params, "sort"), _param(params, "statsPeriod"))
            if len(parts) == 5 and parts[:3] == ["api", "0", "organizations"] and parts[4] == "issues":
                return 200, issues.list_org_issues(store, parts[3], _param(params, "query"), _param(params, "sort"), _param(params, "statsPeriod"))
            if len(parts) == 4 and parts[:3] == ["api", "0", "issues"]:
                return _found(issues.get_issue(store, parts[3]))
            if len(parts) == 5 and parts[:3] == ["api", "0", "issues"] and parts[4] == "events":
                return 200, events.list_issue_events(store, parts[3])
            if len(parts) == 6 and parts[:3] == ["api", "0", "issues"] and parts[4] == "events" and parts[5] == "latest":
                return _found(events.latest_event(store, parts[3]))
            if len(parts) == 7 and parts[:3] == ["api", "0", "projects"] and parts[5] == "events":
                return _found(events.get_event(store, parts[4], parts[6]))
            if len(parts) == 5 and parts[:3] == ["api", "0", "organizations"] and parts[4] == "releases":
                return 200, releases.list_releases(store, parts[3], _param(params, "project"))
            if len(parts) == 6 and parts[:3] == ["api", "0", "organizations"] and parts[4] == "releases":
                return _found(releases.get_release(store, parts[3], urllib.parse.unquote(parts[5]), _param(params, "project")))
            if len(parts) == 5 and parts[:3] == ["api", "0", "issues"] and parts[4] == "suspect-commits":
                return 200, issues.suspect_commits(store, parts[3])
            if len(parts) == 5 and parts[:3] == ["api", "0", "issues"] and parts[4] == "comments":
                return 200, comments.list_comments(store, parts[3])
            if len(parts) == 5 and parts[:3] == ["api", "0", "issues"] and parts[4] == "activity":
                return 200, comments.list_activity(store, parts[3])
            if len(parts) == 6 and parts[:3] == ["api", "0", "projects"] and parts[5] == "ownership":
                return 200, ownership.list_rules(store, parts[4])
            if path == "/api/_clone/state":
                return 200, clone_admin.state_snapshot(store)
            if path == "/api/_clone/mutations":
                return 200, clone_admin.mutations(store)
            return 404, sentry_error("Not found", 404)

        def _handle_post(self, path: str) -> tuple[int, Any]:
            parts = _parts(path)
            payload = self._read_json()
            if len(parts) == 5 and parts[:3] == ["api", "0", "issues"] and parts[4] == "comments":
                text = str(payload.get("text") or payload.get("comment") or "")
                return 201, comments.add_comment(store, parts[3], text)
            return 404, sentry_error("Not found", 404)

        def _handle_put(self, path: str) -> tuple[int, Any]:
            parts = _parts(path)
            if len(parts) == 4 and parts[:3] == ["api", "0", "issues"]:
                return 200, issues.update_issue(store, parts[3], self._read_json())
            return 404, sentry_error("Not found", 404)

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0") or "0")
            if length <= 0:
                return {}
            body = self.rfile.read(length).decode("utf-8")
            data = json.loads(body)
            if not isinstance(data, dict):
                raise ValueError("JSON request body must be an object")
            return data

        def _send(self, status: int, payload: Any) -> None:
            body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return SentryHandler


def _parts(path: str) -> list[str]:
    return [urllib.parse.unquote(part) for part in path.strip("/").split("/") if part]


def _param(params: dict[str, list[str]], name: str) -> str | None:
    values = params.get(name)
    return values[0] if values else None


def _found(item: Any) -> tuple[int, Any]:
    if item is None:
        return 404, sentry_error("Not found", 404)
    return 200, item


def run_server(host: str = "0.0.0.0", port: int = 80, store: SentryStore | None = None) -> ThreadingHTTPServer:
    actual_store = store or SentryStore.from_runtime()
    server = ThreadingHTTPServer((host, port), make_handler(actual_store))
    server.serve_forever()
    return server


def main() -> int:
    host = os.environ.get("SENTRY_CLONE_BIND_HOST", "0.0.0.0")
    port = int(os.environ.get("SENTRY_CLONE_PORT", "80"))
    try:
        run_server(host, port)
    except StateError as exc:
        print(f"sentry-clone: state error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

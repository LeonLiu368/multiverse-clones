from __future__ import annotations

import json
import os
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from . import alerts, annotations, clone_admin, dashboards, datasources, links, query_engine
from .auth import check_admin_authorization, check_authorization, grafana_error
from .state import GaugeStore, StateError


def make_handler(store: GaugeStore) -> type[BaseHTTPRequestHandler]:
    class GaugeHandler(BaseHTTPRequestHandler):
        server_version = "Gauge"
        sys_version = ""

        def log_message(self, format: str, *args: Any) -> None:
            return

        def do_GET(self) -> None:
            self._dispatch("GET")

        def do_POST(self) -> None:
            self._dispatch("POST")

        def _dispatch(self, method: str) -> None:
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path
            params = urllib.parse.parse_qs(parsed.query)

            if path.startswith("/api/_clone/"):
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
                else:
                    status, payload = 405, grafana_error("Method not allowed", 405)
            except ValueError as exc:
                status, payload = 400, grafana_error(str(exc), 400)
            except Exception as exc:
                status, payload = 500, grafana_error(f"Gauge internal error: {type(exc).__name__}", 500)
            self._send(status, payload)

        def _handle_get(self, path: str, params: dict[str, list[str]]) -> tuple[int, Any]:
            if path == "/api/healthz":
                return 200, {"ok": True, "database": "ok", "version": "gauge-local"}
            if path == "/api/user":
                return 200, store.current_user()
            if path == "/api/org":
                return 200, store.org()
            if path == "/api/search":
                return 200, dashboards.search_dashboards(store, _param(params, "query"), _param(params, "type"))
            if path.startswith("/api/dashboards/uid/"):
                uid = path.rsplit("/", 1)[-1]
                item = dashboards.dashboard_response(store, uid)
                return _found(item)
            if path == "/api/datasources":
                return 200, datasources.list_datasources(store)
            if path.startswith("/api/datasources/uid/"):
                uid = path.rsplit("/", 1)[-1]
                return _found(datasources.get_datasource(store, uid))
            if path == "/api/alert-rules":
                return 200, alerts.list_rules(store, _param(params, "state"))
            if path == "/api/alert-instances":
                return 200, alerts.list_instances(store, _param(params, "state"))
            if path.startswith("/api/alert-rules/") and path.endswith("/history"):
                uid = path.split("/api/alert-rules/", 1)[1].rsplit("/history", 1)[0]
                return 200, alerts.state_history(store, uid)
            if path.startswith("/api/alert-rules/"):
                uid = path.rsplit("/", 1)[-1]
                return _found(alerts.get_rule(store, uid))
            if path == "/api/annotations":
                tags = _csv(_param(params, "tags"))
                return 200, annotations.list_annotations(store, _param(params, "dashboardUID") or _param(params, "dashboard"), tags)
            if path == "/api/_clone/state":
                return 200, clone_admin.state_snapshot(store)
            if path == "/api/_clone/mutations":
                return 200, clone_admin.mutations(store)
            return 404, grafana_error("Not found", 404)

        def _handle_post(self, path: str) -> tuple[int, Any]:
            payload = self._read_json()
            if path == "/api/ds/query":
                return 200, query_engine.ds_query(store, payload)
            if path == "/api/annotations":
                created = annotations.create_annotation(store, payload)
                return 200, created
            return 404, grafana_error("Not found", 404)

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

    return GaugeHandler


def _param(params: dict[str, list[str]], name: str) -> str | None:
    values = params.get(name)
    if not values:
        return None
    return values[0]


def _csv(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def _found(item: Any) -> tuple[int, Any]:
    if item is None:
        return 404, grafana_error("Not found", 404)
    return 200, item


def run_server(host: str = "0.0.0.0", port: int = 80, store: GaugeStore | None = None) -> ThreadingHTTPServer:
    actual_store = store or GaugeStore.from_runtime()
    server = ThreadingHTTPServer((host, port), make_handler(actual_store))
    server.serve_forever()
    return server


def main() -> int:
    host = os.environ.get("GAUGE_BIND_HOST", "0.0.0.0")
    port = int(os.environ.get("GAUGE_PORT", "80"))
    try:
        run_server(host, port)
    except StateError as exc:
        print(f"gauge: state error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

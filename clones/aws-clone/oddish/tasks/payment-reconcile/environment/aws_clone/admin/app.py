from __future__ import annotations

import json
import os
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .auth import check_admin_authorization, error
from . import state_snapshot


def make_handler() -> type[BaseHTTPRequestHandler]:
    class AwsCloneHandler(BaseHTTPRequestHandler):
        server_version = "aws-clone"
        sys_version = ""

        def log_message(self, format: str, *args: Any) -> None:
            return

        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path
            params = urllib.parse.parse_qs(parsed.query)
            if path.startswith("/api/_clone/"):
                auth = check_admin_authorization(self.headers.get("Authorization"))
                if not auth.ok:
                    self._send(auth.status, auth.payload)
                    return
            try:
                status, payload = self._handle_get(path, params)
            except KeyError as exc:
                status, payload = 400, error(f"missing required parameter: {exc.args[0]}", 400)
            except Exception as exc:
                status, payload = 500, error(f"aws-clone admin error: {type(exc).__name__}: {exc}", 500)
            self._send(status, payload)

        def _handle_get(self, path: str, params: dict[str, list[str]]) -> tuple[int, Any]:
            if path == "/api/healthz":
                return 200, {"ok": True, "service": "aws-clone", "backend": "localstack"}
            if path == "/api/_clone/state":
                return 200, state_snapshot.state_snapshot()
            if path == "/api/_clone/mutations":
                return 200, state_snapshot.mutation_log()
            if path == "/api/_clone/s3/buckets":
                return 200, state_snapshot.s3_buckets()
            if path == "/api/_clone/s3/object":
                return 200, state_snapshot.s3_object(_required(params, "bucket"), _required(params, "key"))
            if path == "/api/_clone/sqs/messages":
                return 200, state_snapshot.sqs_messages(_required(params, "queue"), int(_param(params, "limit") or "10"))
            if path == "/api/_clone/dynamodb/table":
                return 200, state_snapshot.dynamodb_table(_required(params, "name"))
            if path == "/api/_clone/logs":
                return 200, state_snapshot.logs(_required(params, "group"), _param(params, "pattern"), int(_param(params, "limit") or "100"))
            return 404, error("Not found", 404)

        def _send(self, status: int, payload: Any) -> None:
            body = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return AwsCloneHandler


def _param(params: dict[str, list[str]], name: str) -> str | None:
    values = params.get(name)
    return values[0] if values else None


def _required(params: dict[str, list[str]], name: str) -> str:
    value = _param(params, name)
    if not value:
        raise KeyError(name)
    return value


def run_server(host: str = "0.0.0.0", port: int = 80) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), make_handler())
    server.serve_forever()
    return server


def main() -> int:
    host = os.environ.get("AWS_CLONE_BIND_HOST", "0.0.0.0")
    port = int(os.environ.get("AWS_CLONE_ADMIN_PORT", "80"))
    try:
        run_server(host, port)
    except Exception as exc:
        print(f"aws-clone admin: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

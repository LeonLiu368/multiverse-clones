from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .client import FakePlaneBackend
from .config import load_config
from .errors import WorldIssuesError, redact


ALLOWED_METHODS = {
    "current_user",
    "project_list",
    "project_view",
    "list_states",
    "list_labels",
    "list_cycles",
    "current_cycle",
    "list_modules",
    "issue_list",
    "issue_mine",
    "get_issue",
    "update_issue",
    "add_comment",
    "list_comments",
    "add_link",
    "list_links",
    "list_attachments",
    "list_relations",
    "history_list",
}


class TicketVectorHandler(BaseHTTPRequestHandler):
    backend: FakePlaneBackend

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _send(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send(200, {"ok": True})
            return
        self._send(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:
        if self.path != "/rpc":
            self._send(404, {"ok": False, "error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            request = json.loads(self.rfile.read(length).decode("utf-8"))
            method = str(request.get("method", ""))
            if method not in ALLOWED_METHODS:
                raise WorldIssuesError(f"unsupported ticketvector service method: {method}")
            args = request.get("args") or []
            kwargs = request.get("kwargs") or {}
            if method == "add_comment":
                kwargs.pop("author", None)
            result = getattr(self.backend, method)(*args, **kwargs)
            self._send(200, {"ok": True, "result": result})
        except WorldIssuesError as exc:
            self._send(200, {"ok": False, "error_type": type(exc).__name__, "error": exc.message})
        except Exception as exc:
            self._send(200, {"ok": False, "error_type": type(exc).__name__, "error": str(redact(exc))})


def main() -> None:
    config = load_config()
    host = os.environ.get("WORLD_ISSUES_BIND_HOST", "127.0.0.1")
    port = int(os.environ.get("WORLD_ISSUES_PORT", "8765"))
    TicketVectorHandler.backend = FakePlaneBackend(config, state_file=config.state_file)
    server = ThreadingHTTPServer((host, port), TicketVectorHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()

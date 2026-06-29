from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

from sentry_clone.server.app import make_handler
from sentry_clone.server.state import SentryStore


TOKEN = "test-token-acme-eval"
ADMIN_TOKEN = "test-admin-token-acme-eval"
ROOT = Path(__file__).resolve().parents[1]


def base_state() -> dict[str, Any]:
    with (ROOT / "examples/data/sentry-clone/state.json").open("r", encoding="utf-8") as handle:
        return json.load(handle)


def fresh_state() -> dict[str, Any]:
    return copy.deepcopy(base_state())


class TestServer:
    __test__ = False

    def __init__(self, state: dict[str, Any] | None = None):
        self.store = SentryStore(state or fresh_state())
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.store))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self._old_env: dict[str, str | None] = {}

    def __enter__(self) -> "TestServer":
        for key, value in {
            "SENTRY_AUTH_TOKEN": TOKEN,
            "SENTRY_CLONE_ENABLE_ADMIN_API": "1",
            "SENTRY_CLONE_ADMIN_TOKEN": ADMIN_TOKEN,
            "SENTRY_ORG": "acme",
        }.items():
            self._set_env(key, value)
        self.thread.start()
        return self

    def __exit__(self, *args: Any) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        for key, value in self._old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _set_env(self, key: str, value: str) -> None:
        if key not in self._old_env:
            self._old_env[key] = os.environ.get(key)
        os.environ[key] = value


def api(server_url: str, path: str, *, token: str = TOKEN, method: str = "GET", payload: dict[str, Any] | None = None) -> tuple[int, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(server_url + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        return exc.code, json.loads(body) if body else {}


def run_sentry(server_url: str, args: list[str]) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update({"SENTRY_URL": server_url, "SENTRY_AUTH_TOKEN": TOKEN, "SENTRY_ORG": "acme", "PYTHONPATH": str(ROOT)})
    return subprocess.run([sys.executable, "-m", "sentry_clone.cli.sentry", *args], env=env, text=True, capture_output=True, timeout=15)


def json_out(result: subprocess.CompletedProcess[str]) -> Any:
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)

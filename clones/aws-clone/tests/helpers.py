from __future__ import annotations

import copy
import json
import os
import socket
import subprocess
import sys
import threading
from contextlib import closing
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

from aws_clone.admin.app import make_handler


ADMIN_TOKEN = "test-admin-token-acme-eval"


def example_state_path() -> Path:
    return Path(__file__).resolve().parents[1] / "examples" / "data" / "aws-clone" / "state.json"


def example_state() -> dict[str, Any]:
    return json.loads(example_state_path().read_text(encoding="utf-8"))


def fresh_state() -> dict[str, Any]:
    return copy.deepcopy(example_state())


class TestAdminServer:
    __test__ = False

    def __init__(self, tmp_path: Path, state: dict[str, Any] | None = None):
        self.tmp_path = tmp_path
        self.seed_path = tmp_path / "seed.json"
        self.runtime_path = tmp_path / "runtime.json"
        self.seed_path.write_text(json.dumps(state or fresh_state()), encoding="utf-8")
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler())
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self._old_env: dict[str, str | None] = {}

    def __enter__(self) -> "TestAdminServer":
        self._set_env("AWS_CLONE_ENABLE_ADMIN_API", "1")
        self._set_env("AWS_CLONE_ADMIN_TOKEN", ADMIN_TOKEN)
        self._set_env("AWS_CLONE_STATE_FILE", str(self.seed_path))
        self._set_env("AWS_CLONE_RUNTIME_STATE_FILE", str(self.runtime_path))
        self._set_env("AWS_ENDPOINT_URL", "http://127.0.0.1:1")
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


def run_clonectl(server_url: str, args: list[str], token: str = ADMIN_TOKEN) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        {
            "AWS_CLONE_ADMIN_URL": server_url,
            "AWS_CLONE_ADMIN_TOKEN": token,
            "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
        }
    )
    return subprocess.run([sys.executable, "-m", "aws_clone.cli.aws_clonectl", *args], env=env, text=True, capture_output=True, timeout=15)


def json_out(result: subprocess.CompletedProcess[str]) -> Any:
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def docker_available() -> bool:
    try:
        subprocess.run(["docker", "version"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        return True
    except Exception:
        return False

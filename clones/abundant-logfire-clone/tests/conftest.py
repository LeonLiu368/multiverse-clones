"""Spin up the real gateway (logfire_clone.server) in a background thread over a small
synthetic corpus, so the suite exercises the actual HTTP API + CLI + MCP — all thin
clients of one API. No mocks."""
import importlib
import json
import os
import socket
import tempfile
import threading
import time

import pytest

# A tiny but representative corpus: exceptions across services, an http 500, a clean span,
# and time-window edges. Enough to test query grammar, filtering, and time scoping.
RECORDS = [
    {"start_timestamp": "2026-06-24T22:35:11Z", "exception_type": "asyncpg.exceptions.UndefinedColumnError",
     "exception_message": 'column "locked_at" of relation "queue_slots" does not exist',
     "service_name": "oddish-worker", "url_path": None, "http_response_status_code": None},
    {"start_timestamp": "2026-06-24T22:36:00Z", "exception_type": "asyncpg.exceptions.UndefinedColumnError",
     "exception_message": 'column "locked_at" of relation "queue_slots" does not exist',
     "service_name": "oddish-worker", "url_path": None, "http_response_status_code": None},
    {"start_timestamp": "2026-06-24T22:40:00Z", "exception_type": "fastapi.exceptions.HTTPException",
     "exception_message": "Not Found", "service_name": "oddish-backend",
     "url_path": "/tasks", "http_response_status_code": 500},
    {"start_timestamp": "2026-06-25T00:30:00Z", "exception_type": None, "exception_message": None,
     "service_name": "oddish-frontend-edge", "url_path": "/dashboard", "http_response_status_code": 200},
]

TOKEN = "test-token-acme-eval"


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


@pytest.fixture(scope="session")
def gateway():
    f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump(RECORDS, f)
    f.close()
    port = _free_port()
    os.environ["LOGFIRE_RECORDS"] = f.name
    os.environ["LOGFIRE_PORT"] = str(port)
    os.environ["LOGFIRE_TOKEN"] = TOKEN
    # import after env is set (module loads the corpus at import time)
    import logfire_clone.server as server
    importlib.reload(server)
    t = threading.Thread(target=lambda: server.ThreadingHTTPServer(
        ("127.0.0.1", port), server.Handler).serve_forever(), daemon=True)
    t.start()
    url = f"http://127.0.0.1:{port}"
    # wait for health
    import urllib.request
    for _ in range(50):
        try:
            urllib.request.urlopen(url + "/health", timeout=1)
            break
        except Exception:
            time.sleep(0.1)
    os.environ["LOGFIRE_URL"] = url
    yield {"url": url, "token": TOKEN, "min": "2026-06-24T00:00:00Z"}

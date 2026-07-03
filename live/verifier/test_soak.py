"""Unit tests for the soak/SLO verifier against LOCAL fake SUTs.

Each fake SUT is a tiny stdlib http.server app spun up on an ephemeral port in
a background thread. We point soak.py at it via a short-window config and assert
the reward + reward-basis. No network, no external services.

Scenarios:
  (a) healthy fast app + valid findings           -> PASS   (reward 1.0)
  (b) app that 503s a fraction above the gate      -> FAIL   on error_rate
  (c) app that serializes/slow-writes (loses marker)-> FAIL  on goodput
  (d) missing findings.json                        -> FAIL   even when SLOs pass
  (e) app never comes up                           -> infra_error, reward 0.0

Run:  python -m pytest -q   (from live/verifier/)
"""
import json
import os
import socket
import sys
import tempfile
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import soak  # noqa: E402


# --------------------------------------------------------------------------- #
# Fake SUT plumbing
# --------------------------------------------------------------------------- #
def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class _Store:
    """Shared per-server state: articles by slug."""
    def __init__(self):
        self.lock = threading.Lock()
        self.articles = {}


def make_handler(mode, store, state):
    """mode controls the fault injected. state carries counters."""

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass  # quiet

        def _send(self, code, obj):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path
            if path.startswith("/health"):
                return self._send(200, {"ok": True})
            if path.startswith("/api/articles/"):
                slug = path.rsplit("/", 1)[-1]
                with store.lock:
                    art = store.articles.get(slug)
                if art is None:
                    return self._send(404, {"errors": "not found"})
                return self._send(200, {"article": art})
            if path.startswith("/api/articles"):
                # feed
                if mode == "err503":
                    with state["lock"]:
                        state["n"] += 1
                        n = state["n"]
                    if n % 2 == 0:  # ~50% 503, well above a 0.12 gate
                        return self._send(503, {"errors": "pool timeout"})
                return self._send(200, {"articles": [], "articlesCount": 0})
            return self._send(404, {"errors": "nope"})

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                body = json.loads(raw or b"{}")
            except Exception:
                body = {}

            path = self.path
            if path.startswith("/api/users"):
                # bootstrap register/login -> token
                return self._send(200, {"user": {"token": "tok-" + uuid.uuid4().hex[:8]}})

            if path.startswith("/api/articles"):
                if mode == "err503":
                    with state["lock"]:
                        state["n"] += 1
                        n = state["n"]
                    if n % 2 == 0:
                        return self._send(503, {"errors": "pool timeout"})

                art = (body or {}).get("article", {})
                title = art.get("title", "untitled")
                slug = "slug-" + uuid.uuid4().hex[:10]

                if mode == "slow_lossy":
                    # Serialize + drop the marker: return a 2xx but WITHOUT the
                    # marker in the stored body, so read-back correctness fails
                    # (goodput collapses) and each write is slow.
                    time.sleep(0.25)
                    stored = {"slug": slug, "title": "REDACTED", "body": "REDACTED"}
                    with store.lock:
                        store.articles[slug] = stored
                    return self._send(201, {"article": stored})

                stored = {"slug": slug, "title": title, "body": art.get("body", "")}
                with store.lock:
                    store.articles[slug] = stored
                return self._send(201, {"article": stored})

            return self._send(404, {"errors": "nope"})

    return H


class FakeSUT:
    def __init__(self, mode):
        self.mode = mode
        self.port = _free_port()
        self.store = _Store()
        self.state = {"lock": threading.Lock(), "n": 0}
        handler = make_handler(mode, self.store, self.state)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", self.port), handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def url(self):
        return "http://127.0.0.1:%d" % self.port

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *a):
        self.httpd.shutdown()
        self.httpd.server_close()


# --------------------------------------------------------------------------- #
# Config + run helpers
# --------------------------------------------------------------------------- #
def base_config(target):
    return {
        "target": target,
        "health_path": "/health",
        "health_timeout_s": 5,
        "health_poll_interval_s": 0.2,
        "warmup_s": 0.5,
        "soak_s": 2.0,
        "rps": 40,
        "workers": 16,
        "request_timeout_s": 3,
        "goodput_min": 0.85,
        "error_rate_max": 0.12,
        "min_samples_per_driver": 5,
        "bootstrap": {
            "token_json_path": "user.token",
            "steps": [
                {"method": "POST", "path": "/api/users",
                 "body": {"user": {"username": "u_{marker}", "email": "e_{marker}@x.com",
                                   "password": "pw"}}},
            ],
        },
        "flows": [
            {"name": "write_readback", "kind": "write_readback", "weight": 1.0,
             "write_path": "/api/articles",
             "write_body": {"article": {"title": "{marker}", "body": "b {marker}"}},
             "slug_json_path": "article.slug",
             "read_path_template": "/api/articles/{slug}",
             "headers": {"Authorization": "Token {token}"}},
            {"name": "read_feed", "kind": "read", "weight": 1.0,
             "path": "/api/articles?limit=10", "expect_substring": "articles"},
        ],
        "findings": {
            "required_keys": ["component", "mechanism"],
            "mechanism_regexes": ["pool", "connection|conn"],
            "mechanism_substrings": [],
        },
    }


def write_findings(tmpdir, obj):
    p = os.path.join(tmpdir, "findings.json")
    with open(p, "w") as fh:
        json.dump(obj, fh)
    return p


def good_findings():
    return {"component": "conduit db engine",
            "mechanism": "SQLAlchemy connection pool exhausted (DB_POOL_SIZE=1) "
                         "serializes requests onto one connection"}


def run_soak(cfg_dict, findings_path, reward_dir):
    cfg = soak.SoakConfig.from_dict({k: v for k, v in cfg_dict.items()
                                     if not k.startswith("_")})
    return soak.run(cfg, reward_dir, findings_path, None, None)


def read_reward(reward_dir):
    with open(os.path.join(reward_dir, "reward.txt")) as fh:
        return float(fh.read().strip())


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
def test_a_healthy_fast_app_passes():
    with FakeSUT("ok") as sut, tempfile.TemporaryDirectory() as td:
        cfg = base_config(sut.url)
        fp = write_findings(td, good_findings())
        res = run_soak(cfg, fp, td)
        assert res["infra_error"] is False, res
        assert res["slos_pass"] is True, res["slo"]
        assert res["findings_pass"] is True, res["findings"]
        assert read_reward(td) == 1.0
        assert res["slo"]["overall"]["offered"] > 0


def test_b_error_503_fraction_fails_error_rate():
    with FakeSUT("err503") as sut, tempfile.TemporaryDirectory() as td:
        cfg = base_config(sut.url)
        fp = write_findings(td, good_findings())
        res = run_soak(cfg, fp, td)
        assert res["infra_error"] is False, res
        assert res["slos_pass"] is False, res["slo"]
        assert res["slo"]["overall"]["error_rate"] > cfg["error_rate_max"], res["slo"]
        assert read_reward(td) == 0.0


def test_c_slow_lossy_app_fails_goodput():
    with FakeSUT("slow_lossy") as sut, tempfile.TemporaryDirectory() as td:
        cfg = base_config(sut.url)
        # keep the read flow out so goodput is dominated by the lossy write path
        cfg["flows"] = [cfg["flows"][0]]
        fp = write_findings(td, good_findings())
        res = run_soak(cfg, fp, td)
        assert res["infra_error"] is False, res
        assert res["slos_pass"] is False, res["slo"]
        wb = res["slo"]["per_driver"]["write_readback"]
        assert wb["goodput_ratio"] < cfg["goodput_min"], wb
        assert read_reward(td) == 0.0


def test_d_missing_findings_fails_even_if_slos_pass():
    with FakeSUT("ok") as sut, tempfile.TemporaryDirectory() as td:
        cfg = base_config(sut.url)
        fp = os.path.join(td, "does_not_exist.json")
        res = run_soak(cfg, fp, td)
        assert res["infra_error"] is False, res
        assert res["slos_pass"] is True, res["slo"]     # SLOs are fine
        assert res["findings_pass"] is False, res["findings"]
        assert read_reward(td) == 0.0


def test_d2_wrong_mechanism_findings_fails():
    with FakeSUT("ok") as sut, tempfile.TemporaryDirectory() as td:
        cfg = base_config(sut.url)
        # names a component but the WRONG mechanism (no pool/connection)
        fp = write_findings(td, {"component": "conduit",
                                 "mechanism": "the cache was cold"})
        res = run_soak(cfg, fp, td)
        assert res["slos_pass"] is True, res["slo"]
        assert res["findings_pass"] is False, res["findings"]
        assert read_reward(td) == 0.0


def test_e_app_never_up_is_infra_error():
    port = _free_port()  # nothing listening here
    with tempfile.TemporaryDirectory() as td:
        cfg = base_config("http://127.0.0.1:%d" % port)
        cfg["health_timeout_s"] = 2
        fp = write_findings(td, good_findings())
        res = run_soak(cfg, fp, td)
        assert res["infra_error"] is True, res
        assert res["slos_pass"] is False
        assert read_reward(td) == 0.0
        assert "never became healthy" in res["reason"]


def test_result_json_written_with_reward_basis():
    with FakeSUT("ok") as sut, tempfile.TemporaryDirectory() as td:
        cfg = base_config(sut.url)
        fp = write_findings(td, good_findings())
        run_soak(cfg, fp, td)
        with open(os.path.join(td, "result.json")) as fh:
            result = json.load(fh)
        assert "reward" in result
        assert "slo" in result and "overall" in result["slo"]
        assert "findings" in result
        assert "config" in result
        assert result["slo"]["overall"]["latency_p95_ms"] is not None

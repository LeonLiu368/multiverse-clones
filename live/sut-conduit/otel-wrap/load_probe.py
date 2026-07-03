#!/usr/bin/env python3
"""Concurrent-writer load probe for the Conduit SUT (stdlib only).

Registers (or logs in) one user per writer thread, then each writer POSTs
--requests articles (unique titles). Prints a JSON report: p50/p95/max latency,
error rate, wall time, throughput. Exit code 0 always — callers judge numbers.

  python3 load_probe.py --base http://conduit.web.1:8000 --writers 12 --requests 20 --label faulty
"""
import argparse
import json
import statistics
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid

TIMEOUT = 30


def api(base, method, path, body=None, token=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Token {token}")
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            payload = r.read()
            return time.perf_counter() - t0, r.status, payload
    except urllib.error.HTTPError as e:
        return time.perf_counter() - t0, e.code, e.read()
    except Exception:
        return time.perf_counter() - t0, 0, b""  # timeout / connection error


def get_token(base, username, email, password):
    _, status, payload = api(base, "POST", "/api/users",
                             {"user": {"username": username, "email": email,
                                       "password": password}})
    if status not in (200, 201):  # already registered -> login
        _, status, payload = api(base, "POST", "/api/users/login",
                                 {"user": {"email": email, "password": password}})
    if status not in (200, 201):
        raise RuntimeError(f"auth failed for {username}: HTTP {status} {payload[:200]!r}")
    return json.loads(payload)["user"]["token"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--writers", type=int, default=12)
    ap.add_argument("--requests", type=int, default=20)
    ap.add_argument("--label", default="run")
    ap.add_argument("--mode", choices=["write", "read", "mixed"], default="mixed",
                    help="write: POST /api/articles only; read: GET /api/articles "
                         "pages only; mixed (default): each iteration = 1 write + 1 read")
    ap.add_argument("--max-offset", type=int, default=60,
                    help="readers page through offsets in [0, max-offset)")
    ap.add_argument("--login-every", type=int, default=0,
                    help="if >0, each writer re-logins every N iterations "
                         "(bcrypt verify = real CPU work, like real session churn)")
    args = ap.parse_args()

    tokens = [get_token(args.base, f"writer{i}", f"writer{i}@load.dev", "password123")
              for i in range(args.writers)]

    lats, statuses = [], []
    lock = threading.Lock()

    def one_write(idx, n):
        return api(args.base, "POST", "/api/articles",
                   {"article": {"title": f"load {args.label} w{idx} r{n} {uuid.uuid4().hex[:8]}",
                                "description": "load probe",
                                "body": "concurrent write probe body",
                                "tagList": ["load", f"w{idx}"]}},
                   token=tokens[idx])

    def one_read(idx, n):
        offset = (idx * 7919 + n * 611) % args.max_offset  # spread over pages
        return api(args.base, "GET", f"/api/articles?limit=20&offset={offset}")

    def writer(idx):
        local = []
        for n in range(args.requests):
            if args.login_every and n % args.login_every == 0:
                lat, status, _ = api(args.base, "POST", "/api/users/login",
                                     {"user": {"email": f"writer{idx}@load.dev",
                                               "password": "password123"}})
                local.append((lat, status))
            if args.mode in ("write", "mixed"):
                lat, status, _ = one_write(idx, n)
                local.append((lat, status))
            if args.mode in ("read", "mixed"):
                lat, status, _ = one_read(idx, n)
                local.append((lat, status))
        with lock:
            for lat, status in local:
                lats.append(lat)
                statuses.append(status)

    t0 = time.perf_counter()
    threads = [threading.Thread(target=writer, args=(i,)) for i in range(args.writers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    wall = time.perf_counter() - t0

    lats.sort()
    n = len(lats)
    errors = sum(1 for s in statuses if s not in (200, 201))
    report = {
        "label": args.label,
        "writers": args.writers,
        "requests_per_writer": args.requests,
        "total_requests": n,
        "wall_seconds": round(wall, 2),
        "throughput_rps": round(n / wall, 1),
        "p50_ms": round(statistics.median(lats) * 1000, 1),
        "p95_ms": round(lats[max(0, int(n * 0.95) - 1)] * 1000, 1),
        "max_ms": round(lats[-1] * 1000, 1),
        "errors": errors,
        "error_rate": round(errors / n, 4),
    }
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())

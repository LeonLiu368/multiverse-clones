#!/usr/bin/env python3
"""Seed fixture for the Conduit SUT (stdlib only, idempotent).

Creates 3 users and 6 articles (with tags) via the public API so read flows
have data. Safe to re-run: register falls back to login, article slugs are
deterministic and re-creation conflicts are tolerated.

  python3 seed.py --base http://conduit.web.1:8000
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request

TIMEOUT = 15

USERS = [
    ("alice", "alice@conduit.dev", "password123"),
    ("bob", "bob@conduit.dev", "password123"),
    ("carol", "carol@conduit.dev", "password123"),
]

ARTICLES = [
    ("alice", "Welcome to Conduit", "intro", "First post on the RealWorld app.", ["intro"]),
    ("alice", "Deploying on Dokku", "ops", "git push dokku@dokku:conduit and done.", ["ops", "dokku"]),
    ("alice", "Reading OTel Traces", "otel", "Spans for every request and query.", ["otel"]),
    ("bob", "Postgres Pool Sizing", "db", "min/max connection counts matter.", ["db"]),
    ("bob", "FastAPI in Production", "python", "Workers, pools, and telemetry.", ["python"]),
    ("carol", "Load Testing 101", "perf", "p50 lies, p95 tells the truth.", ["perf"]),
]


def api(base, method, path, body=None, token=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Token {token}")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, {}
    except Exception:
        return 0, {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--wait", type=int, default=60,
                    help="seconds to wait for the app to answer before seeding")
    args = ap.parse_args()

    deadline = time.time() + args.wait
    while True:
        status, _ = api(args.base, "GET", "/api/tags")
        if status == 200:
            break
        if time.time() > deadline:
            print(f"[seed] app never answered on {args.base}", file=sys.stderr)
            return 1
        time.sleep(2)

    tokens = {}
    for username, email, password in USERS:
        status, payload = api(args.base, "POST", "/api/users",
                              {"user": {"username": username, "email": email,
                                        "password": password}})
        if status not in (200, 201):  # already exists -> login
            status, payload = api(args.base, "POST", "/api/users/login",
                                  {"user": {"email": email, "password": password}})
        if status not in (200, 201):
            print(f"[seed] cannot auth {username}: HTTP {status}", file=sys.stderr)
            return 1
        tokens[username] = payload["user"]["token"]
    print(f"[seed] users ready: {', '.join(tokens)}")

    created = 0
    for author, title, desc, body, tags in ARTICLES:
        status, _ = api(args.base, "POST", "/api/articles",
                        {"article": {"title": title, "description": desc,
                                     "body": body, "tagList": tags}},
                        token=tokens[author])
        if status in (200, 201):
            created += 1
    status, payload = api(args.base, "GET", "/api/articles?limit=1")
    print(f"[seed] done: {created} articles created this run "
          f"(list answers HTTP {status})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

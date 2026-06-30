"""`logfire` CLI — a thin client of the Logfire Query API gateway, so an agent queries
telemetry the way an Abundant SWE does (SQL over `records`) instead of hand-rolling curl.

Talks to the gateway at ``$LOGFIRE_URL`` (default ``http://logfire``) with the read token
``$LOGFIRE_TOKEN``. Carries NO data — the records live behind the gateway. Matched pair
with ``logfire-gateway`` (which bakes the records). Read-only.

    logfire query "SELECT exception_type, count(*) n FROM records GROUP BY 1 ORDER BY n DESC"
    logfire exceptions --limit 20
    logfire schema
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request

URL = os.environ.get("LOGFIRE_URL", "http://logfire").rstrip("/")
TOKEN = os.environ.get("LOGFIRE_TOKEN", "test-token-acme-eval")
# The gateway scopes every query to [min,max]; default to a window that covers the baked
# incident corpus. Override per call with --since / LOGFIRE_MIN_TIMESTAMP.
DEFAULT_MIN = os.environ.get("LOGFIRE_MIN_TIMESTAMP", "2026-06-24T00:00:00Z")


def query(sql: str, min_ts: str | None = None, max_ts: str | None = None, limit: int | None = None) -> dict:
    """Run SQL through the gateway's POST /v2/query and return the {schema, data} envelope."""
    body: dict = {"sql": sql, "min_timestamp": min_ts or DEFAULT_MIN}
    if max_ts:
        body["max_timestamp"] = max_ts
    if limit:
        body["limit"] = limit
    req = urllib.request.Request(
        f"{URL}/v2/query",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as r:  # noqa: S310 (trusted internal gateway)
        return json.load(r)


def _print(res: dict) -> None:
    json.dump(res.get("data", res), sys.stdout, default=str, indent=2)
    sys.stdout.write("\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="logfire", description="Query the Logfire telemetry gateway.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    q = sub.add_parser("query", help="run arbitrary SQL over `records`")
    q.add_argument("sql")
    q.add_argument("--since", dest="min_ts", default=None, help="min_timestamp (ISO); default covers the corpus")
    q.add_argument("--until", dest="max_ts", default=None, help="max_timestamp (ISO)")
    q.add_argument("--limit", type=int, default=None)

    e = sub.add_parser("exceptions", help="recent exceptions (type, message, service, path)")
    e.add_argument("--since", dest="min_ts", default=None)
    e.add_argument("--limit", type=int, default=50)

    sub.add_parser("schema", help="the `records` table schema (column names + types)")

    args = ap.parse_args(argv)
    try:
        if args.cmd == "query":
            _print(query(args.sql, args.min_ts, args.max_ts, args.limit))
        elif args.cmd == "exceptions":
            sql = ("SELECT start_timestamp, exception_type, exception_message, service_name, "
                   "url_path, http_response_status_code FROM records WHERE exception_type IS NOT NULL "
                   "ORDER BY start_timestamp DESC")
            _print(query(sql, args.min_ts, None, args.limit))
        elif args.cmd == "schema":
            _print(query("SELECT * FROM records", limit=0).get("schema", {}))
    except urllib.error.HTTPError as ex:  # surface gateway errors verbatim
        sys.stderr.write(f"logfire: {ex.code} {ex.read().decode()[:300]}\n")
        return 1
    except Exception as ex:  # noqa: BLE001
        sys.stderr.write(f"logfire: {type(ex).__name__}: {ex}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

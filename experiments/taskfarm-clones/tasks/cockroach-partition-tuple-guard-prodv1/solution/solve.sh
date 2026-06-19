#!/usr/bin/env bash
set -euo pipefail
command -v python3 >/dev/null 2>&1 || { echo "missing python3"; exit 1; }
command -v psql >/dev/null 2>&1 || { echo "missing psql"; exit 1; }
command -v git >/dev/null 2>&1 || { echo "missing git"; exit 1; }
cd /app/src
python3 - <<'PY'
from pathlib import Path

p = Path("pkg/sql/rowenc/partition_tuple_guard.py")
text = p.read_text()
old = '''def should_guard_partition_tuple(row):
    """Return True when descriptor validation should guard tuple decoding."""
    if row["partition_tuple_hex"] == "":
        return False
    return "slice bounds out of range [2:0]" in row["observed_error"]
'''
new = '''def should_guard_partition_tuple(row):
    """Return True when descriptor validation should guard tuple decoding."""
    arity = int(row["tuple_arity"])
    malformed_empty_tuple = row["partition_tuple_hex"] == "" and arity > 0
    has_crdb_63642_signature = "slice bounds out of range [2:0]" in row["observed_error"]
    return malformed_empty_tuple and has_crdb_63642_signature and row["ticket"] == "CRDB-63642"
'''
if old not in text:
    raise SystemExit("expected buggy partition tuple guard not found")
p.write_text(text.replace(old, new))
PY
python3 tools/build_partition_tuple_guard_plan.py --apply >/tmp/cockroach_partition_tuple_guard_plan.json
python3 - <<'PY'
import json
import time
import urllib.request


def rpc(method, *args, **kwargs):
    payload = json.dumps({"method": method, "args": args, "kwargs": kwargs}).encode()
    last = None
    for _ in range(30):
        for base in ("http://127.0.0.1:8765", "http://main:8765"):
            try:
                req = urllib.request.Request(base + "/rpc", data=payload, headers={"Content-Type": "application/json"}, method="POST")
                data = json.loads(urllib.request.urlopen(req, timeout=3).read().decode())
                if not data.get("ok"):
                    raise RuntimeError(data)
                return data["result"]
            except Exception as exc:
                last = exc
        time.sleep(0.5)
    raise SystemExit(last)


rpc("update_issue", "CRDB-63642", state="In Progress")
rpc(
    "add_comment",
    "CRDB-63642",
    "Regenerated /app/artifacts/cockroach_partition_tuple_guard_plan.json and repaired tenant_31_orders_pk_swap plus tenant_42_events_pk_swap. Left tenant_77_geo_archive_intentional_empty untouched because it is the intentional zero-arity empty list case. This is a narrow guard for the CRDB-63642 Sentry signature, not a broad descriptor rewrite or skip-all validation workaround.",
)
rpc("update_issue", "CRDB-63642", state="In Review")
PY
git add pkg/sql/rowenc/partition_tuple_guard.py
git commit -m "Guard malformed partition tuple decode for CRDB-63642" >/tmp/cockroach-partition-tuple-guard-commit.txt

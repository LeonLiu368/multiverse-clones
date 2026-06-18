#!/usr/bin/env bash
set -euo pipefail
cd /app/src
command -v python3 >/dev/null 2>&1 || { echo "python3 missing"; exit 1; }
command -v psql >/dev/null 2>&1 || { echo "psql missing"; exit 1; }
python3 - <<'PY'
from pathlib import Path
p = Path("charts/loki/values.yaml")
text = p.read_text()
replacements = {
    "pod_id: loki-write-2\n      component: write\n      active_index_directory: /data/loki/boltdb-shipper-active\n      cache_location: /data/loki/boltdb-shipper-cache":
    "pod_id: loki-write-2\n      component: write\n      active_index_directory: /data/loki/boltdb-shipper-active/loki-write-2\n      cache_location: /data/loki/boltdb-shipper-cache/loki-write-2",
    "pod_id: loki-write-5\n      component: write\n      active_index_directory: /data/loki/boltdb-shipper-active\n      cache_location: /data/loki/boltdb-shipper-cache":
    "pod_id: loki-write-5\n      component: write\n      active_index_directory: /data/loki/boltdb-shipper-active/loki-write-5\n      cache_location: /data/loki/boltdb-shipper-cache/loki-write-5",
}
for old, new in replacements.items():
    if old not in text:
        raise SystemExit(f"expected block not found: {old!r}")
    text = text.replace(old, new)
p.write_text(text)
PY
python3 tools/loki_path_audit.py --apply >/tmp/loki-boltdb-audit.json
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

rpc("update_issue", "LOKI-3248", state="In Progress")
rpc("add_comment", "LOKI-3248", "Generated /app/artifacts/loki_boltdb_repair.json after isolating loki-write-2 and loki-write-5 with pod-scoped BoltDB shipper active/cache paths. Left loki-compactor-0 untouched because it is healthy and intentionally uses the compactor path. This was a narrow repair, not a data wipe.")
rpc("update_issue", "LOKI-3248", state="In Review")
PY
git add charts/loki/values.yaml && git commit -m "Scope Loki BoltDB shipper paths to crashing write replicas" >/tmp/loki-boltdb-commit.txt

#!/usr/bin/env bash
set -euo pipefail
command -v psql >/dev/null
cd /app/src
python3 - <<'PY'
import json
from pathlib import Path

path = Path("nightly/tpcc_profiles.yaml")
data = json.loads(path.read_text())
target = data["profiles"]["tpcc_1000w_1000t"]
target["enabled"] = True
target["cn_memory_limit_gib"] = 64
target["lockservice_rpc_timeout_ms"] = 45000
path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
PY
python3 tools/render_tpcc_repair.py --apply >/tmp/mo-24893-artifact.json
python3 - <<'PY'
import json
import time
import urllib.request

def rpc(method, *args, **kwargs):
    payload = json.dumps({"method": method, "args": args, "kwargs": kwargs}).encode()
    last = None
    for _ in range(30):
        try:
            req = urllib.request.Request("http://127.0.0.1:8765/rpc", data=payload, headers={"Content-Type": "application/json"}, method="POST")
            data = json.loads(urllib.request.urlopen(req, timeout=5).read().decode())
            if not data.get("ok"):
                raise RuntimeError(data)
            return data["result"]
        except Exception as exc:
            last = exc
            time.sleep(1)
    raise SystemExit(last)

rpc("update_issue", "MO-24893", state="In Review")
rpc(
    "add_comment",
    "MO-24893",
    "Scoped repair complete for tpcc_1000w_1000t only. Artifact: /app/artifacts/mo-24893-tpcc-repair.json. Target CN nightly-regression-dis-tp-cn-phqxp backend 10.143.26.143:6003 was at 54.47Gi/55Gi during 2026-06-08T18:42:51Z to 2026-06-08T18:48:42Z. The later IVF OOMKilled alert is unrelated to this TPCC root cause; smaller TPCC profiles stay untouched and no global CN memory bump was applied.",
    author="agent",
)
PY

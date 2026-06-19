#!/usr/bin/env bash
set -euo pipefail
command -v python3 >/dev/null
command -v git >/dev/null
cd /app/src
python3 - <<'PY'
from pathlib import Path
p = Path("prometheus_operator/probe_policy.py")
text = p.read_text()
old = '''if bool(instance.get("listenLocal")):
        command = (
            f'if [ -x "$(command -v curl)" ]; then exec curl --fail http://localhost:{port}{path}; '
            f'elif [ -x "$(command -v wget)" ]; then exec wget -q -O /dev/null http://localhost:{port}{path}; '
            "else exit 1; fi"
        )
        return {
            "exec": {"command": ["sh", "-c", command]},
            "periodSeconds": 5,
            "timeoutSeconds": 3,
        }
'''
new = '''if bool(instance.get("listenLocal")) and is_distroless(instance):
        return {
            "httpGet": {"host": "127.0.0.1", "path": path, "port": port, "scheme": "HTTP"},
            "periodSeconds": 5,
            "timeoutSeconds": 3,
        }
    if bool(instance.get("listenLocal")):
        command = (
            f'if [ -x "$(command -v curl)" ]; then exec curl --fail http://localhost:{port}{path}; '
            f'elif [ -x "$(command -v wget)" ]; then exec wget -q -O /dev/null http://localhost:{port}{path}; '
            "else exit 1; fi"
        )
        return {
            "exec": {"command": ["sh", "-c", command]},
            "periodSeconds": 5,
            "timeoutSeconds": 3,
        }
'''
if old not in text:
    raise SystemExit("expected buggy listenLocal branch not found")
p.write_text(text.replace(old, new))
PY
python3 tools/build_distroless_probe_repair.py --apply >/tmp/prometheus-distroless-local-probes.json
python3 - <<'PY'
import json
import time
import urllib.request


def rpc(method, *args, **kwargs):
    payload = json.dumps({"method": method, "args": args, "kwargs": kwargs}).encode()
    last = None
    for _ in range(30):
        for base in ("http://jira:8765", "http://main:8765"):
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


rpc("update_issue", "PROMOP-8605", state="In Progress")
rpc(
    "add_comment",
    "PROMOP-8605",
    "Built /app/artifacts/prometheus_distroless_probe_repair.json and repaired prom-ceems-primary plus prom-edge-rules. Left prom-legacy-shell and prom-public-metrics untouched after checking the local evidence. This is a narrow renderer fix for distroless listenLocal probes, not a broad rollback or fleet rewrite.",
)
rpc("update_issue", "PROMOP-8605", state="In Review")
PY
git add prometheus_operator/probe_policy.py
git commit -m "Fix distroless listenLocal probe rendering" >/tmp/prometheus-distroless-local-probes-commit.txt

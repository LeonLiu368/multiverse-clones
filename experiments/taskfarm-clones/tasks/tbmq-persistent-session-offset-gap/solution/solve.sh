#!/usr/bin/env bash
set -euo pipefail

command -v nodejs >/dev/null 2>&1 || { echo "missing required tool: nodejs" >&2; exit 1; }
command -v psql >/dev/null 2>&1 || { echo "missing required tool: psql" >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "missing required tool: python3" >&2; exit 1; }

cd /app/src

python3 - <<'PY'
from pathlib import Path
path = Path("src/persistentSessionPlanner.js")
text = path.read_text()
old = """  const graceWindowSeconds = options.graceWindowSeconds || 10;
  const inferredStart = Math.max(retryOffset + 1, nextStart - graceWindowSeconds);
  const inferredEnd = nextStart - 1;
"""
new = """  const inferredStart = retryOffset + 1;
  const inferredEnd = nextStart - 1;
"""
if old not in text:
    raise SystemExit("expected buggy reconnect-window logic not found")
path.write_text(text.replace(old, new))
PY

nodejs tools/replayPersistentSession.js --apply

python3 - <<'PY'
import json
import time
import urllib.request


def rpc(method, *args, **kwargs):
    payload = json.dumps({"method": method, "args": args, "kwargs": kwargs}).encode()
    last = None
    for _ in range(30):
        try:
            req = urllib.request.Request(
                "http://127.0.0.1:8765/rpc",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            data = json.loads(urllib.request.urlopen(req, timeout=3).read().decode())
            if data.get("ok"):
                return data["result"]
            last = data
        except Exception as exc:
            last = exc
        time.sleep(0.5)
    raise SystemExit(last)


rpc("update_issue", "TBMQ-320", state="In Progress")
rpc(
    "add_comment",
    "TBMQ-320",
    "Rebuilt /app/artifacts/tbmq_persistent_session_replay_plan.json; repaired mqtt_gap_3216_3262 and edge_bridge_8801_8817. Left mqtt_gap_packet_2708_dup0_followup untouched because it is the DUP/PubAck follow-up symptom, not a committed-over offset gap. This is a narrow replay-before-commit repair, not a broad consumer group reset.",
)
rpc("update_issue", "TBMQ-320", state="In Review")
PY

#!/usr/bin/env bash
# Oracle: count messages containing "testing" across every channel, via the gateway, and write it.
set -euo pipefail
python3 - <<'PY'
import os, json, urllib.parse, urllib.request
BASE = os.environ.get("SLACK_API_URL", "http://localhost").rstrip("/")
TOK = os.environ.get("SLACK_BOT_TOKEN", "xoxp-acme-eval-0001")

def api(method, **params):
    url = f"{BASE}/api/{method}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {TOK}"})
    return json.load(urllib.request.urlopen(req, timeout=15))

n = 0
for c in api("conversations.list").get("channels", []):
    for m in api("conversations.history", channel=c["id"], limit=1000).get("messages", []):
        if "testing" in (m.get("text") or "").lower():
            n += 1
with open("/workspace/answer.txt", "w") as f:
    f.write(str(n))
print("oracle wrote answer:", n)
PY

#!/usr/bin/env bash
# Oracle: compute the three facts via the gateway and write them in the required format.
set -euo pipefail
python3 - <<'PY'
import os, json, urllib.parse, urllib.request
BASE = os.environ.get("SLACK_API_URL", "http://localhost").rstrip("/")
TOK = os.environ.get("SLACK_BOT_TOKEN", "xoxp-acme-eval-0001")

def api(method, **params):
    url = f"{BASE}/api/{method}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {TOK}"})
    return json.load(urllib.request.urlopen(req, timeout=30))

chans = api("conversations.list").get("channels", [])
by_name = {c["name"]: c["id"] for c in chans}
msgs = api("conversations.history", channel=by_name["testing-survey-responses"], limit=1000).get("messages", [])

answers = {
    "channels": len(chans),
    "tsr_messages": len(msgs),
    "tsr_survey": sum(1 for m in msgs if "survey" in (m.get("text") or "").lower()),
}
with open("/workspace/answers.txt", "w") as f:
    for k, v in answers.items():
        f.write(f"{k}={v}\n")
print("oracle wrote:", answers)
PY

#!/bin/bash
# Oracle: count messages containing 'testing' across every channel (via the gateway).
set -uo pipefail
python3 - <<'PY'
import os, json, urllib.request, urllib.parse
BASE = os.environ.get("SLACK_API_URL","http://localhost").rstrip("/")
TOK = os.environ.get("SLACK_BOT_TOKEN","xoxp-acme-eval-0001")
def call(m, **p):
    u=f"{BASE}/api/{m}?"+urllib.parse.urlencode(p)
    return json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"Authorization":f"Bearer {TOK}"})))
cnt=0
for ch in call("conversations.list").get("channels",[]) or []:
    for msg in call("conversations.history", channel=ch["id"], limit=1000).get("messages",[]) or []:
        if "testing" in (msg.get("text","") or "").lower(): cnt+=1
os.makedirs("/workspace", exist_ok=True); open("/workspace/answer.txt","w").write(str(cnt)+"\n")
print("oracle counted 'testing':", cnt)
PY

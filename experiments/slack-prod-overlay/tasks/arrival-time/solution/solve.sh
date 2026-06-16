#!/usr/bin/env bash
# Oracle: read the workspace through the gateway, find the planted arrival note in #engineering,
# extract the time, write it. Mirrors what an agent does with the slack tools.
set -uo pipefail
python3 - <<'PY'
import os, json, re, urllib.request, urllib.parse
BASE = os.environ.get("SLACK_API_URL", "http://localhost").rstrip("/")
TOK = os.environ.get("SLACK_BOT_TOKEN", "xoxp-acme-eval-0001")
def call(method, **params):
    url = f"{BASE}/api/{method}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {TOK}"})
    return json.load(urllib.request.urlopen(req))
text = ""
try:
    r = call("search.messages", query="payments hotfix")
    for m in (r.get("messages", {}) or {}).get("matches", []) or []:
        if "coming in" in (m.get("text") or "").lower():
            text = m["text"]; break
except Exception:
    pass
if not text:
    r = call("conversations.history", channel="C72917EF6C1", limit=50)
    for m in r.get("messages", []):
        if "coming in" in (m.get("text") or "").lower():
            text = m["text"]; break
mm = re.search(r'(\d{1,2})\s*pm', text.lower())
ans = f"{int(mm.group(1)) + 12:02d}:00" if mm else ""
os.makedirs("/workspace", exist_ok=True)
open("/workspace/answer.txt", "w").write(ans + "\n")
print("oracle wrote:", ans, "| from:", text[:70])
PY

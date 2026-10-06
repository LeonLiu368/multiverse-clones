#!/bin/bash
# Oracle: base build number for v8.5.0 (real prod #defect-and-blocker-thunderdome message) + the
# delta from the planted #engineering changelog message.
set -uo pipefail
python3 - <<'PY'
import os, json, re, urllib.request, urllib.parse
BASE = os.environ.get("SLACK_API_URL","http://localhost").rstrip("/")
TOK = os.environ.get("SLACK_BOT_TOKEN","xoxp-acme-eval-0001")
def call(m, **p):
    u=f"{BASE}/api/{m}?"+urllib.parse.urlencode(p)
    return json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"Authorization":f"Bearer {TOK}"})))
def matches(q):
    try: return (call("search.messages", query=q).get("messages",{}) or {}).get("matches",[]) or []
    except Exception: return []
base=None
for m in matches("v8.5.0 build"):
    mm=re.search(r'8\.5\.0\s+build\s+#(\d+)', m.get("text","") or "", re.I)
    if mm: base=int(mm.group(1)); break
delta=None
for m in matches("builds after"):
    mm=re.search(r'(\d+)\s+builds?\s+after', m.get("text","") or "", re.I)
    if mm: delta=int(mm.group(1)); break
ans = str((base or 0)+(delta or 0))
os.makedirs("/workspace", exist_ok=True); open("/workspace/answer.txt","w").write(ans+"\n")
print(f"oracle: base={base} delta={delta} -> {ans}")
PY

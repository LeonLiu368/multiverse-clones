#!/bin/bash
# Oracle: (1) recent overlay note in #release-status -> the v9.0.0 go-live date; (2) the author of the
# unique "feature and code-complete" message in #product, resolved via users.info.
set -uo pipefail
python3 - <<'PY'
import os, json, re, urllib.request, urllib.parse
BASE = os.environ.get("SLACK_API_URL","http://localhost").rstrip("/")
TOK = os.environ.get("SLACK_BOT_TOKEN","xoxp-acme-eval-0001")
def call(m, **p):
    u=f"{BASE}/api/{m}?"+urllib.parse.urlencode(p)
    return json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"Authorization":f"Bearer {TOK}"})))
def matches(q):
    return (call("search.messages", query=q).get("messages",{}) or {}).get("matches",[]) or []
# part 1: the recent v9.0.0 scheduling note (overlay)
rdate=""
for mm in matches("v9.0.0 go live"):
    t=mm.get("text","") or ""
    d=re.search(r'go live on ([A-Z][a-z]+ \d{1,2})', t)
    if d: rdate=d.group(1); break
# part 2: author of the "feature and code-complete" message
author=""
for mm in matches("feature and code-complete"):
    uid=mm.get("user")
    if uid:
        author=(call("users.info", user=uid).get("user",{}) or {}).get("real_name",""); break
os.makedirs("/workspace", exist_ok=True)
open("/workspace/answer.txt","w").write(f"release_date={rdate}\nauthor={author}\n")
print("oracle:", repr(rdate), repr(author))
PY

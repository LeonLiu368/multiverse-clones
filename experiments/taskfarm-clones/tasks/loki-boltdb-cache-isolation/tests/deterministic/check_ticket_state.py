import json
import re
import time
import urllib.request

ISSUE = "LOKI-3248"

def rpc(method, *args, **kwargs):
    payload = json.dumps({"method": method, "args": args, "kwargs": kwargs}).encode()
    last = None
    for _ in range(30):
        for base in ("http://jira:8765", "http://127.0.0.1:8765", "http://main:8765"):
            try:
                req = urllib.request.Request(base + "/rpc", data=payload, headers={"Content-Type": "application/json"}, method="POST")
                data = json.loads(urllib.request.urlopen(req, timeout=3).read().decode())
                assert data.get("ok"), data
                return data["result"]
            except Exception as exc:
                last = exc
        time.sleep(0.5)
    raise AssertionError(last)

issue = rpc("get_issue", ISSUE)
assert issue.get("state", {}).get("name") == "In Review", issue
closed_ref = rpc("get_issue", "LOKI-3219")
assert closed_ref.get("state", {}).get("name") == "Closed", closed_ref
text = "\n".join(c.get("body", "") for c in rpc("list_comments", ISSUE) if c.get("author", {}).get("handle") == "agent").lower()
for term in ["loki-write-2", "loki-write-5", "/app/artifacts/loki_boltdb_repair.json", "loki-compactor-0"]:
    assert term in text, text
assert re.search(r"narrow|scoped|only the write replicas|not a .*wipe|avoid.*wipe", text), text
print("ticket ok")

import json
import re
import time
import urllib.request


ISSUE = "PROMOP-8605"


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
comments = rpc("list_comments", ISSUE)
text = "\n".join(c.get("body", "") for c in comments if c.get("author", {}).get("handle") == "agent").lower()
for term in [
    "prometheus_distroless_probe_repair.json",
    "prom-ceems-primary",
    "prom-edge-rules",
    "prom-legacy-shell",
    "prom-public-metrics",
]:
    assert term in text, text
assert re.search(r"narrow|scoped|only", text), text
assert re.search(r"broad rollback|fleet rewrite|not .*rollback|not .*fleet", text), text
print("ticket ok")

import json
import re
import time
import urllib.request


ISSUE = "CRDB-63963"


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
agent_comments = [c.get("body", "") for c in rpc("list_comments", ISSUE) if c.get("author", {}).get("handle") == "agent"]
text = "\n".join(agent_comments).lower()
for term in [
    "193",
    "211",
    "244",
    "305",
    "318",
    "descriptor_backref_repair.json",
]:
    assert term in text, text
assert re.search(r"missing|not found", text), text
assert re.search(r"validation|validate", text), text
assert re.search(r"scoped|narrow|only|not .*scrub|avoid.*scrub|not .*disable|leave", text), text
print("ticket ok")

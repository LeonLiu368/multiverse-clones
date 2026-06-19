import json
import re
import time
import urllib.request


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


issue = rpc("get_issue", "MO-24893")
assert issue.get("state", {}).get("name") == "In Review", issue
agent_text = "\n".join(
    comment.get("body", "")
    for comment in rpc("list_comments", "MO-24893")
    if comment.get("author", {}).get("handle") == "agent"
).lower()
for term in [
    "/app/artifacts/mo-24893-tpcc-repair.json",
    "tpcc_1000w_1000t",
    "nightly-regression-dis-tp-cn-phqxp",
    "2026-06-08t18:42:51z",
    "2026-06-08t18:48:42z",
]:
    assert term in agent_text, agent_text
assert re.search(r"ivf.*oom.*(unrelated|not.*root|later|separate)|not.*oomkilled|no.*oomkilled", agent_text), agent_text
assert re.search(r"scoped|narrow|only.*1000w|not.*global|avoid.*broad", agent_text), agent_text

noise = rpc("get_issue", "MO-24788")
assert noise.get("state", {}).get("name") == "Done", noise
noise_agent_comments = [
    comment for comment in rpc("list_comments", "MO-24788")
    if comment.get("author", {}).get("handle") == "agent"
]
assert not noise_agent_comments, noise_agent_comments
print("ticket ok")

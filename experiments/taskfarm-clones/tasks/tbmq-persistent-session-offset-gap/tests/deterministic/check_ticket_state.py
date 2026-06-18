import json
import re
import time
import urllib.request


ISSUE = "TBMQ-320"
ARTIFACT_PATH = "/app" + "/artifacts/tbmq_persistent_session_replay_plan.json"


def rpc(method, *args, **kwargs):
    payload = json.dumps({"method": method, "args": args, "kwargs": kwargs}).encode()
    last = None
    for _ in range(30):
      for base in ("http://jira:8765", "http://127.0.0.1:8765", "http://main:8765"):
        try:
            req = urllib.request.Request(
                base + "/rpc",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
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
text = "\n".join(
    comment.get("body", "")
    for comment in comments
    if comment.get("author", {}).get("handle") == "agent"
).lower()

for term in [
    "mqtt_gap_3216_3262",
    "edge_bridge_8801_8817",
    "mqtt_gap_packet_2708_dup0_followup",
    ARTIFACT_PATH,
]:
    assert term in text, text

assert re.search(r"narrow|scoped|not a broad|avoid(?:ed)? a full|not.*reset", text), text
print("ticket ok")

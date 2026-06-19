import json
import re
import time
import urllib.request


ISSUE = "CRDB-63642"


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
text = "\n".join(
    comment.get("body", "")
    for comment in rpc("list_comments", ISSUE)
    if comment.get("author", {}).get("handle") == "agent"
).lower()
for term in [
    "tenant_31_orders_pk_swap",
    "tenant_42_events_pk_swap",
    "tenant_77_geo_archive_intentional_empty",
    "cockroach_partition_tuple_guard_plan.json",
]:
    assert term in text, text
assert re.search(r"narrow|scoped|not a broad|avoid.*broad|skip all", text), text
print("ticket ok")

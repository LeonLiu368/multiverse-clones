import json
import os
import time
import urllib.request

from workflow_assertions import any_pr_reference, select_incident_pr

ISSUE = 'OPS-501'
REPO = 'acme/payment-retry-policy'
BODY_TERMS = ['payment', 'retry', 'capped']
DISTRACTORS = ['OPS-819', 'OPS-822', 'OPS-823']
ARTIFACT_TERMS = ['replay', 'artifact', 'payment_retry_replay', 'scheduled_retries', 'unsafe_retries', 'capped_retries']


def rpc(method, *args, **kwargs):
    candidates = []
    if os.environ.get("PLANE_BASE_URL"):
        candidates.append(os.environ["PLANE_BASE_URL"].rstrip("/"))
    candidates.extend(["http://main:8765", "http://127.0.0.1:8765"])
    payload = json.dumps({"method": method, "args": args, "kwargs": kwargs}).encode("utf-8")
    last = None
    for _ in range(30):
        for base in candidates:
            req = urllib.request.Request(base + "/rpc", data=payload, headers={"Content-Type": "application/json"}, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=3) as response:
                    data = json.loads(response.read().decode("utf-8"))
                assert data.get("ok"), data
                return data.get("result")
            except Exception as exc:
                last = exc
        time.sleep(0.5)
    raise AssertionError(f"ticketvector RPC unavailable: {last}")


def state_name(issue):
    state = issue.get("state", {})
    return state.get("name") if isinstance(state, dict) else state


def link_url(link):
    return str(link.get("url", ""))


def has_review_evidence(comments, links, pr):
    link_values = [link_url(link) for link in links]
    all_link_text = "\n".join(link_values).lower()
    has_git_or_pr_link = any_pr_reference(link_values, pr, REPO) or any(
        url.lower().startswith(("commit:", "pr:", "github:", "http://github/", "https://github.local/", "https://github.com/"))
        for url in link_values
    )
    for comment in comments:
        if comment.get("author", {}).get("handle") != "agent":
            continue
        body = comment.get("body", "")
        lower = body.lower()
        mentions_fix = any(term in lower for term in ["fix", "fixed", "implemented", "updated", "applied", "ready", "recovered", "merged", "resolved", "corrected", "aligned", "shipped"])
        mentions_verification = any(term in lower for term in ["verified", "verification", "test", "tests", "evidence", "handoff", "prove", "proves", "proven", "validated", "confirm", "confirms"])
        mentions_artifact = any(term in lower for term in ARTIFACT_TERMS)
        mentions_pr = any_pr_reference([body], pr, REPO) or has_git_or_pr_link
        if mentions_fix and mentions_artifact and mentions_pr and (mentions_verification or has_git_or_pr_link or "evidence" in all_link_text):
            return True
    return False


pr = select_incident_pr(REPO, ISSUE, BODY_TERMS)
issue = rpc("get_issue", ISSUE)
comments = rpc("list_comments", ISSUE)
links = rpc("list_links", ISSUE) + issue.get("links", [])
history = rpc("history_list", ISSUE)

assert state_name(issue) == "In Review", issue.get("state")
assert any(a.get("handle") == "agent" for a in issue.get("assignees", [])), issue.get("assignees")
assert has_review_evidence(comments, links, pr), {"comments": comments, "links": links, "selected_pr": pr}

reviewed = any(
    h.get("action") in {"issue.update", "issue.transition"}
    and h.get("after", {}).get("state", {}).get("name") == "In Review"
    for h in history
)
started_or_direct_review = any(
    h.get("action") in {"issue.update", "issue.start"}
    and h.get("after", {}).get("state", {}).get("name") == "In Progress"
    for h in history
)
direct_todo_to_review = any(
    h.get("before", {}).get("state", {}).get("name") in {"Todo", "Backlog"}
    and h.get("after", {}).get("state", {}).get("name") == "In Review"
    for h in history
)
assert reviewed, history
assert started_or_direct_review or direct_todo_to_review, history

for identifier in DISTRACTORS:
    other = rpc("get_issue", identifier)
    assert state_name(other) in ("Backlog", "Todo"), other
    other_comments = rpc("list_comments", identifier)
    other_links = rpc("list_links", identifier) + other.get("links", [])
    assert not any(c.get("author", {}).get("handle") == "agent" for c in other_comments), {"issue": identifier, "comments": other_comments}
    assert not any(str(link.get("url", "")).startswith(("commit:", "pr:", "http://github/", "https://github.local/")) for link in other_links), {"issue": identifier, "links": other_links}
print("ticket workflow checks passed")

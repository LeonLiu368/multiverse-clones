#!/usr/bin/env python3
# Deterministic generator for the :prod-v1 corpus baked into the gateway image.
#
# Run from the repo root: `python3 corpus/build_corpus.py` -> writes corpus/state.json
# (byte-identical on every run). The corpus is a SUPERSET of the empty example fixture:
# it keeps payments-api / PAYMENTS-501 (so existing smoke holds) and adds a checkout-web
# project + more issues for a realistic shared corpus.
#
# This generator and its output live ONLY in the repo + the gateway image, never in the
# agent image (the agent Dockerfile strips sentry_clone.server and copies no corpus), so
# the seeded answer is neither greppable nor recomputable on the agent (R2.k leak rule).
import json, copy, pathlib

base = json.load(open("examples/data/sentry-clone/state.json"))
corpus = copy.deepcopy(base)
corpus["meta"]["corpus"] = "prod-v1"

# Add a second team + project
corpus["teams"].append({"id": "team-checkout", "slug": "checkout", "name": "Checkout"})
corpus["projects"].append({
    "id": "proj-checkout", "slug": "checkout-web", "name": "Checkout Web",
    "platform": "javascript", "team_slug": "checkout",
})

# Releases for checkout-web
corpus["releases"].append({
    "version": "checkout-web@2026.06.07.4",
    "project_slug": "checkout-web",
    "dateCreated": "2026-06-07T09:00:00Z",
    "lastDeploy": {"environment": "production", "dateFinished": "2026-06-07T09:05:00Z", "commit": "ck00aa1"},
    "commits": [{"id": "ck00aa1", "repository": "acme/checkout-web",
                 "message": "Add idempotency key to charge submit", "author": "dev2@example.local",
                 "files": ["checkout/charge.js"]}],
})

# Two more issues on checkout-web (one unresolved, one ignored) + one more on payments-api
new_issues = [
    {
        "id": "2001", "shortId": "CHECKOUT-12", "project_slug": "checkout-web",
        "title": "TypeError: cannot read properties of undefined (reading 'token')",
        "culprit": "checkout/charge.js in submitCharge",
        "level": "error", "status": "unresolved", "substatus": "ongoing", "priority": "high",
        "type": "error", "firstSeen": "2026-06-07T08:30:00Z", "lastSeen": "2026-06-07T08:59:00Z",
        "count": 21, "userCount": 9, "environment": "production",
        "tags": {"service": "checkout", "route": "/charge", "status_code": "500",
                 "error_type": "type_error", "release": "checkout-web@2026.06.07.4",
                 "environment": "production"},
        "assignedTo": None, "owner": {"type": "team", "slug": "checkout"},
        "suspectCommits": [{"id": "ck00aa1", "repository": "acme/checkout-web",
                            "message": "Add idempotency key to charge submit",
                            "author": "dev2@example.local", "files": ["checkout/charge.js"]}],
        "latestEventId": "evt-2001-latest",
    },
    {
        "id": "2002", "shortId": "CHECKOUT-7", "project_slug": "checkout-web",
        "title": "Warning: deprecated payment provider SDK",
        "culprit": "checkout/provider.js in initSdk",
        "level": "warning", "status": "ignored", "substatus": "until_escalating", "priority": "low",
        "type": "default", "firstSeen": "2026-06-01T00:00:00Z", "lastSeen": "2026-06-06T00:00:00Z",
        "count": 200, "userCount": 50, "environment": "production",
        "tags": {"service": "checkout", "error_type": "deprecation",
                 "release": "checkout-web@2026.06.07.4", "environment": "production"},
        "assignedTo": {"type": "team", "slug": "checkout"},
        "owner": {"type": "team", "slug": "checkout"},
        "suspectCommits": [], "latestEventId": "evt-2002-latest", "ignoreReason": "noise",
    },
    {
        "id": "1002", "shortId": "PAYMENTS-510", "project_slug": "payments-api",
        "title": "TimeoutError: upstream provider timeout",
        "culprit": "payments.gateway in call_provider",
        "level": "error", "status": "unresolved", "substatus": "ongoing", "priority": "medium",
        "type": "error", "firstSeen": "2026-06-07T11:50:00Z", "lastSeen": "2026-06-07T11:58:00Z",
        "count": 8, "userCount": 5, "environment": "staging",
        "tags": {"service": "payments", "route": "/charge", "status_code": "504",
                 "error_type": "timeout", "release": "payments-api@2026.06.07.1",
                 "environment": "staging"},
        "assignedTo": None, "owner": {"type": "team", "slug": "payments"},
        "suspectCommits": [], "latestEventId": "evt-1002-latest",
    },
]
corpus["issues"].extend(new_issues)

def mk_event(eid, issue_id, proj, ts, exc_type, value, file, func, line, ctx, env, rel):
    return {
        "id": eid, "issue_id": issue_id, "project_slug": proj, "timestamp": ts,
        "message": f"{exc_type}: {value}",
        "exception": {"type": exc_type, "value": value, "mechanism": {"handled": False}},
        "stacktrace": {"frames": [
            {"filename": file, "function": func, "lineno": line,
             "context_line": ctx, "in_app": True}]},
        "breadcrumbs": [{"timestamp": ts, "category": "app", "level": "info",
                         "message": f"context for {issue_id}"}],
        "contexts": {"runtime": {"name": "node" if proj == "checkout-web" else "CPython",
                                 "version": "20" if proj == "checkout-web" else "3.11"}},
        "user": {"id": f"cust-{issue_id}", "email": "redacted@example.local"},
        "tags": {"release": rel, "environment": env, "error_type": "x"},
    }

corpus["events"].extend([
    mk_event("evt-2001-latest", "2001", "checkout-web", "2026-06-07T08:59:10Z",
             "TypeError", "cannot read properties of undefined (reading 'token')",
             "checkout/charge.js", "submitCharge", 57, "const t = session.token;",
             "production", "checkout-web@2026.06.07.4"),
    mk_event("evt-2002-latest", "2002", "checkout-web", "2026-06-06T00:00:00Z",
             "Warning", "deprecated payment provider SDK",
             "checkout/provider.js", "initSdk", 12, "sdk.legacyInit();",
             "production", "checkout-web@2026.06.07.4"),
    mk_event("evt-1002-latest", "1002", "payments-api", "2026-06-07T11:58:05Z",
             "TimeoutError", "upstream provider timeout",
             "payments/gateway.py", "call_provider", 71, "resp = client.post(url, timeout=2)",
             "staging", "payments-api@2026.06.07.1"),
])

corpus["ownership_rules"].append(
    {"project_slug": "checkout-web", "match": "checkout/**", "owner": "team:checkout"})

out = pathlib.Path("corpus/state.json")
out.write_text(json.dumps(corpus, indent=2, sort_keys=True) + "\n")

# Validate against the real validator
import sys
sys.path.insert(0, ".")
from sentry_clone.server.state import validate_state
validate_state(json.loads(out.read_text()))
print("corpus valid:", len(corpus["issues"]), "issues,", len(corpus["projects"]), "projects,", len(corpus["events"]), "events")

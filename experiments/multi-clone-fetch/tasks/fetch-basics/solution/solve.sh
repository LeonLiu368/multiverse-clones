#!/usr/bin/env bash
# Oracle: fetch the seven facts through the clone CLIs/APIs and write /app/report.json.
# -e so a failing CLI (e.g. a missing dep) aborts loudly instead of falling through
# to the "wrote report.json" line and leaving the file unwritten.
set -euo pipefail

python3 - <<'PY'
import json, re, subprocess, urllib.request

def jira_rpc(method, *args, **kwargs):
    payload = json.dumps({"method": method, "args": args, "kwargs": kwargs}).encode()
    req = urllib.request.Request("http://jira:8765/rpc", data=payload,
                                 headers={"Content-Type": "application/json"}, method="POST")
    data = json.loads(urllib.request.urlopen(req, timeout=5).read().decode())
    if not data.get("ok"):
        raise RuntimeError(data)
    return data["result"]

def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=60).stdout

# 1 + 2: Jira issue titles (seeded WEB-100, prod ENG-13)
jira_seeded = jira_rpc("get_issue", "WEB-100")["title"]
jira_prod = jira_rpc("get_issue", "ENG-13")["title"]

# 3: Slack — the planted feature flag in #engineering
flag = re.search(r"EXPORT_FLAG_\d+", run(["slack", "search", "EXPORT_FLAG"])).group(0)

# 4: Slack — the prod #general channel id
chans = json.loads(run(["slack", "channels", "--json"]))
chans = chans if isinstance(chans, list) else chans.get("channels", [])
general_id = next(c["id"] for c in chans if c.get("name") == "general")

# 5: GitHub — the open issue title in acme/reporting-export
issues = json.loads(run(["gh", "api", "repos/acme/reporting-export/issues?state=open"]))
issues = issues if isinstance(issues, list) else issues.get("issues", [])
gh_title = next(i["title"] for i in issues if not i.get("pull_request"))

# 6: Gauge — batch_size from export-service logs
batch = re.search(r"batch_size=(\d+)",
                  run(["gcx", "logs", "query", "--since", "720h",
                       '{service="export-service"} |= "batch_size"'])).group(1)

# 7: Sentry — EXP-501 title
sentry_title = ""
for line in run(["sentry", "issues", "get", "EXP-501"]).splitlines():
    if line.strip().lower().startswith("title:"):
        sentry_title = line.split(":", 1)[1].strip()
        break

report = {
    "jira_seeded_issue_title": jira_seeded,
    "jira_prod_issue_title": jira_prod,
    "slack_seeded_flag": flag,
    "slack_prod_general_channel_id": general_id,
    "github_open_issue_title": gh_title,
    "gauge_batch_size": batch,
    "sentry_issue_title": sentry_title,
}
with open("/app/report.json", "w") as fh:
    json.dump(report, fh, indent=2)
print(json.dumps(report, indent=2))
PY

echo "oracle: wrote /app/report.json"

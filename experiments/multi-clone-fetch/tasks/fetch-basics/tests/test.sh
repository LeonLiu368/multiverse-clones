#!/usr/bin/env bash
# Verifier for multi-clone-fetch/fetch-basics.
#
# reward=1 iff /app/report.json exists and ALL seven values equal the ground truth, where
# ground truth is recomputed by re-reading each fact through the SAME tools/APIs the agent
# has (never by trusting the file's narration):
#   jira_seeded_issue_title        <- jira  /rpc get_issue WEB-100 .title
#   jira_prod_issue_title          <- jira  /rpc get_issue ENG-13  .title
#   slack_seeded_flag              <- slack search "EXPORT_FLAG"  (regex EXPORT_FLAG_\d+)
#   slack_prod_general_channel_id  <- slack channels --json       (#general .id)
#   github_open_issue_title        <- gh api repos/acme/reporting-export/issues?state=open
#   gauge_batch_size               <- gcx logs query export-service (regex batch_size=\d+)
#   sentry_issue_title             <- sentry issues get EXP-501    (title: line)
set -uo pipefail
mkdir -p /logs/verifier 2>/dev/null || true
REPORT="${REPORT_FILE:-/app/report.json}"

python3 - "$REPORT" <<'PY' > /logs/verifier/check.log 2>&1
import json, re, subprocess, sys, urllib.request, time

report_path = sys.argv[1]

def fail(msg):
    print("FAIL:", msg)

def norm(s):
    return re.sub(r"\s+", " ", str(s)).strip().casefold()

# ---- load the agent's report ----
try:
    with open(report_path) as fh:
        report = json.load(fh)
    assert isinstance(report, dict)
except Exception as e:
    print(f"reward=0  (could not read {report_path}: {e})")
    open("/logs/verifier/reward.txt", "w").write("0\n")
    sys.exit(0)

# ---- ground-truth readers (through the tools) ----
def jira_rpc(method, *args, **kwargs):
    payload = json.dumps({"method": method, "args": args, "kwargs": kwargs}).encode()
    last = None
    for _ in range(30):
        for base in ("http://jira:8765", "http://127.0.0.1:8765"):
            try:
                req = urllib.request.Request(base + "/rpc", data=payload,
                                             headers={"Content-Type": "application/json"}, method="POST")
                data = json.loads(urllib.request.urlopen(req, timeout=4).read().decode())
                if data.get("ok"):
                    return data["result"]
            except Exception as exc:
                last = exc
        time.sleep(0.5)
    raise RuntimeError(f"jira rpc {method} failed: {last}")

def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=60)

def gt_jira_title(ident):
    return jira_rpc("get_issue", ident).get("title", "")

def gt_slack_flag():
    out = run(["slack", "search", "EXPORT_FLAG"]).stdout
    m = re.search(r"EXPORT_FLAG_\d+", out)
    return m.group(0) if m else ""

def gt_slack_general_id():
    out = run(["slack", "channels", "--json"]).stdout
    chans = json.loads(out)
    chans = chans if isinstance(chans, list) else chans.get("channels", [])
    for c in chans:
        if c.get("name") == "general":
            return c.get("id", "")
    return ""

def gt_github_open_issue_title():
    out = run(["gh", "api", "repos/acme/reporting-export/issues?state=open"]).stdout
    issues = json.loads(out)
    issues = issues if isinstance(issues, list) else issues.get("issues", [])
    titles = [i.get("title", "") for i in issues if not i.get("pull_request")]
    return titles[0] if titles else ""

def gt_gauge_batch_size():
    out = run(["gcx", "logs", "query", "--since", "720h", '{service="export-service"} |= "batch_size"']).stdout
    m = re.search(r"batch_size=(\d+)", out)
    return m.group(1) if m else ""

def gt_sentry_title():
    out = run(["sentry", "issues", "get", "EXP-501"]).stdout
    for line in out.splitlines():
        if line.strip().lower().startswith("title:"):
            return line.split(":", 1)[1].strip()
    return ""

# ---- comparisons ----
ok = True

def check_str(key, expected):
    global ok
    got = report.get(key)
    if got is None:
        fail(f"{key}: missing from report"); ok = False; return
    if norm(got) != norm(expected) or not norm(expected):
        fail(f"{key}: report={got!r} expected={expected!r}"); ok = False
    else:
        print(f"ok   {key}: {got!r}")

def check_int(key, expected):
    global ok
    got = report.get(key)
    try:
        if str(int(str(got).strip())) != str(int(str(expected).strip())) or expected == "":
            raise ValueError
        print(f"ok   {key}: {got!r}")
    except Exception:
        fail(f"{key}: report={got!r} expected={expected!r}"); ok = False

try:
    check_str("jira_seeded_issue_title", gt_jira_title("WEB-100"))
    check_str("jira_prod_issue_title", gt_jira_title("ENG-13"))
    check_str("slack_seeded_flag", gt_slack_flag())
    check_str("slack_prod_general_channel_id", gt_slack_general_id())
    check_str("github_open_issue_title", gt_github_open_issue_title())
    check_int("gauge_batch_size", gt_gauge_batch_size())
    check_str("sentry_issue_title", gt_sentry_title())
except Exception as e:
    fail(f"ground-truth read error: {e}"); ok = False

reward = 1 if ok else 0
print(f"reward={reward}")
open("/logs/verifier/reward.txt", "w").write(f"{reward}\n")
PY

cat /logs/verifier/check.log || true
REWARD="$(cat /logs/verifier/reward.txt 2>/dev/null || echo 0)"
echo "reward=${REWARD}"
exit 0

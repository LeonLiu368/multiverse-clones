#!/usr/bin/env bash
# Verifier for jira-status-lookup.
#
# reward=1 iff /workspace/answer.txt reports the status AND assignee of ENG-2016 that match the
# GROUND TRUTH fetched live from the `jira` sidecar (we never trust the agent's narration — we
# recompute the truth and compare). nop (empty/absent answer) -> 0; oracle -> 1.
set -uo pipefail
mkdir -p /logs/verifier 2>/dev/null || true

ANSWER="/workspace/answer.txt"

# Ground truth, live from the sidecar over HTTP.
truth_json="$(jira issue view ENG-2016 --json 2>/dev/null || echo '{}')"

reward="$(python3 - "$truth_json" "$ANSWER" <<'PY'
import json, sys, os, re

truth = json.loads(sys.argv[1]) if sys.argv[1].strip() else {}
true_status = (truth.get("state") or {}).get("name", "").strip()
assignees = truth.get("assignees") or []
true_assignee = (assignees[0]["name"] if assignees else "Unassigned").strip()

path = sys.argv[2]
text = ""
if os.path.exists(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()

def field(name):
    m = re.search(rf"(?im)^\s*{name}\s*:\s*(.+?)\s*$", text)
    return m.group(1).strip() if m else ""

ans_status = field("status")
ans_assignee = field("assignee")

# Need a real truth to grade against; bail to 0 if the sidecar gave us nothing.
if not true_status:
    print("0"); raise SystemExit

ok = (ans_status.lower() == true_status.lower()
      and ans_assignee.lower() == true_assignee.lower())
sys.stderr.write(
    f"[verifier] truth status={true_status!r} assignee={true_assignee!r}; "
    f"answer status={ans_status!r} assignee={ans_assignee!r}; ok={ok}\n")
print("1" if ok else "0")
PY
)"

echo "$reward" > /logs/verifier/reward.txt
echo "reward=$reward"
exit 0

#!/usr/bin/env bash
# Oracle: look up ENG-2016 through the jira CLI (over HTTP to the sidecar) and write the answer.
set -euo pipefail

json="$(jira issue view ENG-2016 --json)"
python3 - "$json" > /workspace/answer.txt <<'PY'
import json, sys
d = json.loads(sys.argv[1])
status = (d.get("state") or {}).get("name", "")
assignees = d.get("assignees") or []
assignee = assignees[0]["name"] if assignees else "Unassigned"
print(f"status: {status}")
print(f"assignee: {assignee}")
PY

echo "oracle: wrote /workspace/answer.txt"
cat /workspace/answer.txt

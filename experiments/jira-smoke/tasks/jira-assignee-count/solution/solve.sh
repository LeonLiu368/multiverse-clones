#!/usr/bin/env bash
# Oracle: count WEB issues assigned to priya.singh through the jira CLI (over HTTP) and write it.
set -euo pipefail

json="$(jira issue query --assignee priya.singh --json)"
python3 - "$json" > /workspace/answer.txt <<'PY'
import json, sys
d = json.loads(sys.argv[1])
results = d.get("results", d if isinstance(d, list) else [])
print(f"count: {len(results)}")
PY

echo "oracle: wrote /workspace/answer.txt"
cat /workspace/answer.txt

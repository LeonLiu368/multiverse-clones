#!/usr/bin/env bash
# Oracle: find the unresponsive-checkout WEB issue via the jira CLI (over HTTP), transition it to
# Done, add a comment, and record the identifier — the same write→read path the verifier reads back.
set -euo pipefail

target="$(python3 - <<'PY'
import json, subprocess
out = subprocess.run(["jira", "jql", 'text ~ "checkout"', "--json"], capture_output=True, text=True)
d = json.loads(out.stdout)
results = d.get("results", d if isinstance(d, list) else [])
for issue in results:
    title = (issue.get("title") or "").lower()
    if "checkout" in title and ("unrespons" in title or "button" in title):
        print(issue["identifier"]); break
PY
)"

if [ -z "${target:-}" ]; then
  echo "oracle: could not find the checkout issue" >&2
  exit 1
fi

jira issue transition "$target" "Done" >/dev/null
jira issue comment add "$target" --body "Fix shipped: checkout button now responsive on mobile Safari." >/dev/null
echo "issue: $target" > /workspace/answer.txt

echo "oracle: closed $target"
cat /workspace/answer.txt

#!/usr/bin/env bash
# Verifier for jira-transition-roundtrip (write→read round-trip, R5.2).
#
# reward=1 iff, read LIVE from the `jira` sidecar over HTTP (we never trust the agent's narration):
#   1. /workspace/answer.txt names the correct issue (the unresponsive-checkout bug, WEB-7), AND
#   2. that issue's state is now "Done" (the agent's transition is observable on a later read), AND
#   3. that issue has at least one NEW comment (the agent's comment add is observable too).
# nop (no mutation, empty answer) -> 0; oracle -> 1.
set -uo pipefail
mkdir -p /logs/verifier 2>/dev/null || true

ANSWER="/workspace/answer.txt"

reward="$(python3 - "$ANSWER" <<'PY'
import json, os, re, subprocess, sys

def jira(*args):
    out = subprocess.run(["jira", *args, "--json"], capture_output=True, text=True)
    try:
        return json.loads(out.stdout)
    except Exception:
        return None

# Ground-truth target: the WEB issue describing the unresponsive checkout button. Resolve it LIVE
# by searching, so the verifier never hardcodes the identifier from disk.
target = None
res = jira("jql", 'text ~ "checkout"')
results = (res or {}).get("results", []) if isinstance(res, dict) else (res or [])
for issue in results:
    title = (issue.get("title") or "").lower()
    if "checkout" in title and ("unrespons" in title or "button" in title):
        target = issue["identifier"]
        break

reward = 0
if target:
    view = jira("issue", "view", target, "--comments")
    if isinstance(view, dict):
        state_name = (view.get("state") or {}).get("name", "")
        comments = view.get("comments", [])
        # answer.txt must name the same issue
        path = sys.argv[1]
        text = open(path, encoding="utf-8", errors="replace").read() if os.path.exists(path) else ""
        m = re.search(r"(WEB-\d+)", text, re.I)
        answer_id = m.group(1).upper() if m else None

        state_ok = state_name.lower() == "done"
        comment_ok = len(comments) >= 1
        answer_ok = answer_id == target
        sys.stderr.write(
            f"[verifier] target={target} state={state_name!r} comments={len(comments)} "
            f"answer={answer_id} -> state_ok={state_ok} comment_ok={comment_ok} answer_ok={answer_ok}\n"
        )
        if state_ok and comment_ok and answer_ok:
            reward = 1
print(reward)
PY
)"

echo "$reward" > /logs/verifier/reward.txt
echo "reward=$reward"
exit 0

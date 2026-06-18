#!/usr/bin/env bash
# Verifier for jira-assignee-count.
#
# reward=1 iff /workspace/answer.txt reports the count of WEB issues assigned to priya.singh that
# matches the GROUND TRUTH computed live from the `jira` sidecar (we recompute, never trust the
# agent's narration). nop (empty/absent answer) -> 0; oracle -> 1.
set -uo pipefail
mkdir -p /logs/verifier 2>/dev/null || true

ANSWER="/workspace/answer.txt"

# Ground truth, live from the sidecar over HTTP. Paginate to be safe (default page is 50; the WEB
# project has far fewer, but follow next_cursor anyway so this stays correct for bigger projects).
truth="$(python3 - <<'PY'
import json, subprocess
total, cursor = 0, None
while True:
    cmd = ["jira", "issue", "query", "--assignee", "priya.singh", "--json"]
    if cursor:
        cmd += ["--cursor", str(cursor)]
    out = subprocess.run(cmd, capture_output=True, text=True)
    try:
        d = json.loads(out.stdout)
    except Exception:
        print(""); raise SystemExit
    results = d.get("results", d if isinstance(d, list) else [])
    total += len(results)
    cursor = d.get("next_cursor") if isinstance(d, dict) else None
    if not cursor:
        break
print(total)
PY
)"

reward="$(python3 - "$truth" "$ANSWER" <<'PY'
import sys, os, re
truth = sys.argv[1].strip()
if truth == "":
    print("0"); raise SystemExit
true_n = int(truth)

path = sys.argv[2]
text = ""
if os.path.exists(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()

# Accept "count: N" or a bare integer.
m = re.search(r"(?im)^\s*count\s*:\s*(\d+)\s*$", text)
if not m:
    m = re.search(r"(?<!\d)(\d+)(?!\d)", text)
ans_n = int(m.group(1)) if m else None

ok = ans_n is not None and ans_n == true_n
sys.stderr.write(f"[verifier] truth={true_n} answer={ans_n} ok={ok}\n")
print("1" if ok else "0")
PY
)"

echo "$reward" > /logs/verifier/reward.txt
echo "reward=$reward"
exit 0

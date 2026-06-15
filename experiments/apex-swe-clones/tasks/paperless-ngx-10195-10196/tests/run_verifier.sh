#!/bin/bash
# Apply the hidden test.patch, run the upstream test command, and grade by the exact
# F2P/P2P tests from test_metadata.json. reward=1 iff every F2P and P2P test PASSED.
set -uo pipefail
mkdir -p /logs/verifier
cd /app/repo || { echo 0 > /logs/verifier/reward.txt; exit 0; }
git config --global --add safe.directory /app/repo 2>/dev/null || true

git apply /tests/test.patch 2>/logs/verifier/patch.err || patch -p1 < /tests/test.patch 2>>/logs/verifier/patch.err || {
  echo "failed to apply test.patch" >> /logs/verifier/patch.err; echo 0 > /logs/verifier/reward.txt; exit 0; }

LOG=/logs/verifier/test-output.txt
# Run the upstream test command (its node ids are correct by construction), verbosely.
CMD="$(python3 -c "import json;print(json.load(open('/tests/test_metadata.json'))['test_command'])")"
echo "test_command: $CMD" | tee -a "$LOG"
set +e
eval "$CMD -v -p no:cacheprovider" >>"$LOG" 2>&1
set -e
tail -40 "$LOG" || true

# Grade: every F2P+P2P node id must appear as PASSED. Convert APEX dotted ids
# (module.path.Class[.Nested]::method) to pytest node ids (path/file.py::Class::method).
python3 - <<'PY'
import json, re
m = json.load(open("/tests/test_metadata.json"))
log = open("/logs/verifier/test-output.txt", encoding="utf-8", errors="replace").read()

def to_nodeid(x):
    pre, _, method = x.partition("::")
    parts = pre.split(".")
    i = len(parts)
    while i > 0 and parts[i-1][:1].isupper():   # trailing CapWords = class(es)
        i -= 1
    module, classes = parts[:i], parts[i:]
    nid = "/".join(module) + ".py"
    for c in classes:
        nid += "::" + c
    if method:
        nid += "::" + method
    return nid

required = [to_nodeid(x) for x in (m.get("FAIL_TO_PASS", []) + m.get("PASS_TO_PASS", []))]
missing, failed = [], []
for nid in required:
    if re.search(re.escape(nid) + r"\s+PASSED", log):
        continue
    if re.search(re.escape(nid) + r"\s+(FAILED|ERROR)", log):
        failed.append(nid)
    else:
        missing.append(nid)

ok = not missing and not failed
print(f"required={len(required)} failed={len(failed)} missing={len(missing)} -> reward={'1' if ok else '0'}")
for n in (failed + missing)[:15]:
    print("  NOT-PASSED:", n)
open("/logs/verifier/reward.txt", "w").write("1\n" if ok else "0\n")
PY
echo "reward=$(cat /logs/verifier/reward.txt)"
exit 0

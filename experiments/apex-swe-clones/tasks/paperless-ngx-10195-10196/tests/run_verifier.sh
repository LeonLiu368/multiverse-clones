#!/bin/bash
# Apply the hidden test.patch, run the upstream test suite, and grade by the exact
# F2P/P2P node ids from test_metadata.json. reward=1 iff every F2P and P2P test passes.
set -uo pipefail
mkdir -p /logs/verifier
cd /app/repo || { echo 0 > /logs/verifier/reward.txt; exit 0; }
git config --global --add safe.directory /app/repo 2>/dev/null || true

git apply /tests/test.patch 2>/logs/verifier/patch.err || patch -p1 < /tests/test.patch 2>>/logs/verifier/patch.err || {
  echo "failed to apply test.patch" >> /logs/verifier/patch.err; echo 0 > /logs/verifier/reward.txt; exit 0; }

LOG=/logs/verifier/test-output.txt
python3 - <<'PY' > /logs/verifier/nodeids.txt
import json
m=json.load(open("/tests/test_metadata.json"))
def to_nodeid(x):
    mod, _, rest = x.partition("::")
    return mod.replace(".", "/") + ".py" + ("::" + rest if rest else "")
ids=[to_nodeid(x) for x in (m.get("FAIL_TO_PASS",[])+m.get("PASS_TO_PASS",[]))]
print("\n".join(ids))
PY
mapfile -t NODEIDS < /logs/verifier/nodeids.txt
echo "grading ${#NODEIDS[@]} F2P+P2P tests" | tee -a "$LOG"

set +e
python3 -m pytest "${NODEIDS[@]}" -p no:cacheprovider -q >"$LOG" 2>&1
RC=$?
set -e
tail -25 "$LOG" || true

if [ "$RC" -eq 0 ]; then echo 1 > /logs/verifier/reward.txt; else echo 0 > /logs/verifier/reward.txt; fi
echo "reward=$(cat /logs/verifier/reward.txt)"
exit 0

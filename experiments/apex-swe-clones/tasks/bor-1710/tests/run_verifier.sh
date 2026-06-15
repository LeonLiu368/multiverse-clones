#!/bin/bash
# Apply the hidden test.patch, run the upstream Go tests, and grade by the exact F2P/P2P
# test ids from test_metadata.json. reward=1 iff every F2P and P2P test PASSED.
set -uo pipefail
mkdir -p /logs/verifier
cd /app/repo || { echo 0 > /logs/verifier/reward.txt; exit 0; }
git config --global --add safe.directory /app/repo 2>/dev/null || true

git apply /tests/test.patch 2>/logs/verifier/patch.err || patch -p1 < /tests/test.patch 2>>/logs/verifier/patch.err || {
  echo "failed to apply test.patch" >> /logs/verifier/patch.err; echo 0 > /logs/verifier/reward.txt; exit 0; }

LOG=/logs/verifier/test-output.txt
# Packages from the upstream test_command; restrict to the required tests via -run for speed.
PKGS="$(python3 -c "import json,re;c=json.load(open('/tests/test_metadata.json'))['test_command'];print(' '.join(re.findall(r'(\./\S+)',c)))")"
RUN_RE="$(python3 -c "
import json
m=json.load(open('/tests/test_metadata.json'))
tops=set()
for x in m.get('FAIL_TO_PASS',[])+m.get('PASS_TO_PASS',[]):
    name=x.split('::',1)[1] if '::' in x else x
    tops.add(name.split('/',1)[0])
print('^(' + '|'.join(sorted(tops)) + ')\$')
")"
echo "packages: $PKGS" | tee -a "$LOG"
echo "run-regex: ${RUN_RE:0:120}..." | tee -a "$LOG"

set +e
go test $PKGS -run "$RUN_RE" -count=1 -v -timeout 30m -skip TestCheckRunEnv >>"$LOG" 2>&1
set -e
tail -20 "$LOG" || true

python3 - <<'PY'
import json, re
m = json.load(open("/tests/test_metadata.json"))
log = open("/logs/verifier/test-output.txt", encoding="utf-8", errors="replace").read()
required = []
for x in m.get("FAIL_TO_PASS", []) + m.get("PASS_TO_PASS", []):
    required.append(x.split("::", 1)[1] if "::" in x else x)
missing, failed = [], []
for name in required:
    if (f"--- PASS: {name} (" in log) or (f"--- PASS: {name}\t" in log):
        continue
    if (f"--- FAIL: {name} (" in log) or (f"--- FAIL: {name}\t" in log):
        failed.append(name)
    else:
        missing.append(name)
ok = not missing and not failed
print(f"required={len(required)} failed={len(failed)} missing={len(missing)} -> reward={'1' if ok else '0'}")
for n in (failed + missing)[:15]:
    print("  NOT-PASSED:", n)
open("/logs/verifier/reward.txt", "w").write("1\n" if ok else "0\n")
PY
echo "reward=$(cat /logs/verifier/reward.txt)"
exit 0

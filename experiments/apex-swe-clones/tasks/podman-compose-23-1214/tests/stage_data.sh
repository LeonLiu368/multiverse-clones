#!/bin/bash
# Restore the pristine test files (discard any agent edits) before grading.
set -uo pipefail
cd /app/repo || exit 0
git config --global --add safe.directory /app/repo 2>/dev/null || true
python3 - <<'PY' || true
import json
m=json.load(open("/tests/test_metadata.json"))
for f in m.get("test_files",[]):
    import subprocess; subprocess.run(["git","checkout","--",f],cwd="/app/repo")
PY
exit 0

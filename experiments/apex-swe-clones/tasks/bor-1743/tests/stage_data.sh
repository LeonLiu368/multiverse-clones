#!/bin/bash
set -uo pipefail
cd /app/repo || exit 0
git config --global --add safe.directory /app/repo 2>/dev/null || true
python3 - <<'PY' || true
import json,subprocess
m=json.load(open("/tests/test_metadata.json"))
for f in m.get("test_files",[]):
    subprocess.run(["git","checkout","--",f],cwd="/app/repo")
PY
exit 0

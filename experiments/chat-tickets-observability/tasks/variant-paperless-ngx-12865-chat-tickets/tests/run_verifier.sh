#!/bin/bash
# Deterministic verification. Recomputes truth by running the PR's real regression test
# (the F2P test) against the candidate-modified /app/repo. Writes the canonical reward to
# /logs/verifier/reward.txt (1 iff the F2P test passes, else 0).
set -uo pipefail
mkdir -p /logs/verifier
cd /app/repo || { echo 0 > /logs/verifier/reward.txt; exit 0; }
git config --global --add safe.directory /app/repo 2>/dev/null || true

# Install the HIDDEN regression test (never present in the agent image).
git apply /tests/test.patch 2>/logs/verifier/patch.err || patch -p1 < /tests/test.patch 2>>/logs/verifier/patch.err || {
  echo "failed to apply test.patch" >> /logs/verifier/patch.err
  echo 0 > /logs/verifier/reward.txt
  exit 0
}

LOG=/logs/verifier/test-output.txt
export UV_PROJECT_ENVIRONMENT=/app/repo/.venv
export DJANGO_SETTINGS_MODULE=paperless.settings
set +e
uv run --no-sync python -m pytest \
  src/documents/tests/search/test_backend.py::TestWriteBatch::test_writer_released_when_commit_fails \
  -o addopts='' -p no:cacheprovider -q >"$LOG" 2>&1
RC=$?
set -e
tail -20 "$LOG" || true

if [ "$RC" -eq 0 ]; then echo 1 > /logs/verifier/reward.txt; else echo 0 > /logs/verifier/reward.txt; fi
echo "reward=$(cat /logs/verifier/reward.txt)"
exit 0

#!/bin/bash
# Trusted: restore the pristine test tree (discard any agent edits to test files) so the
# candidate cannot weaken the verifier, and create verifier scratch.
set -uo pipefail
cd /app/repo || exit 0
git config --global --add safe.directory /app/repo 2>/dev/null || true
# The hidden regression test is a NEW file; remove any candidate-created file at that path
# and revert tracked test files so the hidden patch applies cleanly.
for f in src/documents/tests/search/test_lock_backoff.py; do
  git checkout -- "$f" 2>/dev/null || true
  git ls-files --error-unmatch "$f" >/dev/null 2>&1 || rm -f "$f"
done
mkdir -p /tmp/verifier-scratch && chmod 0700 /tmp/verifier-scratch
exit 0

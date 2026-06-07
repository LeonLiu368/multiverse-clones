#!/bin/bash
# reward=1 iff candidate ratelimit/ passes trusted suite + hidden config grader.
set -uo pipefail
mkdir -p /logs/verifier
TRUSTED="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/trusted"

GRADE="/tmp/grade.$$"
rm -rf "$GRADE"; mkdir -p "$GRADE"
cp -r /workspace/ratelimit "$GRADE/ratelimit"
cp "$TRUSTED"/test_bucket.py "$TRUSTED"/test_middleware.py "$TRUSTED"/test_grade_bucket.py "$GRADE/"

cd "$GRADE"
if python -m pytest -q -p no:cacheprovider >/logs/verifier/pytest.log 2>&1; then
  echo "1" > /logs/verifier/reward.txt
  echo "reward=1 (candidate ratelimit passes the trusted suite, including hidden config grading)"
else
  echo "0" > /logs/verifier/reward.txt
  echo "reward=0 (trusted suite failing)"
  tail -25 /logs/verifier/pytest.log
fi
rm -rf "$GRADE"
exit 0

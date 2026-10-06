#!/bin/bash
# reward=1 iff candidate events/ passes trusted suite + hidden v2-schema grader.
set -uo pipefail
mkdir -p /logs/verifier
TRUSTED="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/trusted"

GRADE="/tmp/grade.$$"
rm -rf "$GRADE"; mkdir -p "$GRADE"
cp -r /workspace/events "$GRADE/events"
cp "$TRUSTED"/test_publisher.py "$TRUSTED"/test_pipeline.py "$TRUSTED"/test_grade_publisher.py "$GRADE/"

cd "$GRADE"
if python3 -m pytest -q -p no:cacheprovider >/logs/verifier/pytest.log 2>&1; then
  echo "1" > /logs/verifier/reward.txt
  echo "reward=1 (candidate events passes the trusted suite, including hidden v2-schema grading)"
else
  echo "0" > /logs/verifier/reward.txt
  echo "reward=0 (trusted suite failing)"
  tail -25 /logs/verifier/pytest.log
fi
rm -rf "$GRADE"
exit 0

#!/usr/bin/env bash
set -uo pipefail
mkdir -p /logs/verifier
rm -f /logs/verifier/reward.txt /logs/verifier/metrics.json /logs/verifier/reward.json /logs/verifier/test.log

# The hidden upstream test ships only in this verifier image and is copied into
# the checkout here, at verify time, so the agent can never read it or tailor
# code to it. If the copy fails the run is invalid: fail closed rather than let
# the pre-existing upstream suite pass without the hidden test.
if ! cp /tests/graphql_test.go /app/repo/api/graphql/graphql_test.go >> /logs/verifier/test.log 2>&1; then
  echo "verifier setup failed: could not stage the hidden test" >> /logs/verifier/test.log
  echo '{"code_tests_passed": false, "ticket_state_passed": false, "partial_score": 0}' > /logs/verifier/metrics.json
  echo 0 > /logs/verifier/reward.txt
  exit 0
fi

# Two scored checks, both required: the hidden upstream tests pass against the
# candidate's code, and the tracker workflow was completed correctly.
code_tests=0
ticket_state=0
(cd /app/repo && go test ./api/graphql -count=1 -v) >> /logs/verifier/test.log 2>&1 && code_tests=1
python3 /tests/check_ticket_state.py >> /logs/verifier/test.log 2>&1 && ticket_state=1

reward=0
if [ "$code_tests" -eq 1 ] && [ "$ticket_state" -eq 1 ]; then
  reward=1
fi

# reward.txt and partial_score are binary; the per-check booleans are kept in
# metrics.json for debugging only.
printf '{\n  "code_tests_passed": %s,\n  "ticket_state_passed": %s,\n  "partial_score": %s\n}\n' \
  "$([ "$code_tests" -eq 1 ] && echo true || echo false)" \
  "$([ "$ticket_state" -eq 1 ] && echo true || echo false)" \
  "$reward" > /logs/verifier/metrics.json
echo "$reward" > /logs/verifier/reward.txt

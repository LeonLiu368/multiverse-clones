#!/usr/bin/env bash
set -uo pipefail
mkdir -p /logs/verifier
rm -f /logs/verifier/reward.txt /logs/verifier/metrics.json /logs/verifier/reward.json /logs/verifier/test.log

# The hidden upstream test ships only in this verifier image and is copied into
# the checkout here, at verify time, so the agent can never read it or tailor
# code to it. If the copy fails the run is invalid: fail closed.
if ! { mkdir -p /app/repo/src/documents/tests/search && cp /tests/test_query.py /app/repo/src/documents/tests/search/test_query.py; } >> /logs/verifier/test.log 2>&1; then
  echo "verifier setup failed: could not stage the hidden test" >> /logs/verifier/test.log
  echo '{"code_tests_passed": false, "ticket_state_passed": false, "partial_score": 0}' > /logs/verifier/metrics.json
  echo 0 > /logs/verifier/reward.txt
  exit 0
fi

run_code_tests() {
  cd /app/repo
  export UV_PROJECT_ENVIRONMENT=/opt/venv
  export DJANGO_SETTINGS_MODULE=paperless.settings
  (uv sync --all-groups || uv sync --frozen --all-extras || uv sync) >/tmp/uvsync.log 2>&1 || true
  uv run --no-sync pytest src/documents/tests/search/test_query.py -rA
}

# Two scored checks, both required: the hidden upstream tests pass against the
# candidate's code, and the tracker workflow was completed correctly.
code_tests=0
ticket_state=0
(run_code_tests) >> /logs/verifier/test.log 2>&1 && code_tests=1
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

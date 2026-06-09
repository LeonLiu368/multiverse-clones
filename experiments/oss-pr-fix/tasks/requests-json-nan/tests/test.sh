#!/usr/bin/env bash
# Verifier for requests-json-nan (write-the-fix + PR task).
# Reward 1 iff the agent opened a PR against main AND the code on that PR's
# head passes BOTH the existing tests (P2P) and the hidden NaN/Infinity tests
# (F2P). The verifier supplies its own authoritative copies of both test files,
# so the agent can only influence the result through the source code.
set -uo pipefail

LOG_DIR="/logs/verifier"
mkdir -p "$LOG_DIR" 2>/dev/null || LOG_DIR="${TMPDIR:-/tmp}/verifier"
mkdir -p "$LOG_DIR" 2>/dev/null || true
VERIFIER_DIR="/verifier"
mkdir -p "$VERIFIER_DIR" 2>/dev/null || VERIFIER_DIR=""

write_reward() {
  local v="$1"
  echo "$v" > reward.txt 2>/dev/null || true
  echo "$v" > "$LOG_DIR/reward.txt" 2>/dev/null || true
  [ -n "$VERIFIER_DIR" ] && echo "$v" > "$VERIFIER_DIR/reward.txt" 2>/dev/null || true
}
write_reward 0

R=acme/api-service
REPO=api-service
TOK="$(cat /run/secrets/token 2>/dev/null || echo "${GH_TOKEN:-}")"

# ── 1. locate the agent's PR (prefer an open PR; fall back to a merged one) ───
PR_NUM=""
HEAD_REF=""
USE_MAIN=0
for _ in $(seq 1 15); do
  PR_NUM=$(gh pr list -R "$R" --state open --base main --json number --jq '.[0].number' 2>/dev/null)
  [ -n "$PR_NUM" ] && break
  sleep 2
done

if [ -n "$PR_NUM" ]; then
  HEAD_REF=$(gh pr view "$PR_NUM" -R "$R" --json headRefName --jq '.headRefName' 2>/dev/null)
else
  merged=$(gh api "repos/$R/pulls?state=closed&base=main" 2>/dev/null \
    | python3 -c 'import sys,json; xs=json.load(sys.stdin); print(int(any(x.get("merged") for x in xs)))' 2>/dev/null)
  if [ "${merged:-0}" = "1" ]; then
    USE_MAIN=1
  else
    echo "no PR found on $R -> reward 0"
    write_reward 0
    exit 0
  fi
fi

# ── 2. check out the code under test ─────────────────────────────────────────
work="$(mktemp -d)"
git clone -q "http://acme:${TOK}@github/acme/${REPO}.git" "$work/repo" 2>/dev/null || {
  echo "clone failed -> reward 0"; write_reward 0; exit 0; }
cd "$work/repo"

if [ "$USE_MAIN" = "1" ]; then
  git checkout -q main 2>/dev/null
else
  git fetch -q origin "$HEAD_REF" 2>/dev/null && git checkout -q FETCH_HEAD 2>/dev/null || {
    echo "could not check out PR head $HEAD_REF -> reward 0"; write_reward 0; exit 0; }
fi

# ── 3. install authoritative tests (overwrite anything the agent shipped) ─────
rm -rf tests
mkdir -p tests
: > tests/__init__.py

cat > tests/test_basic.py << 'PYEOF'
import json
import unittest

from requests.models import PreparedRequest


class TestPrepareBody(unittest.TestCase):
    def test_valid_json_body_is_bytes(self):
        p = PreparedRequest()
        p.prepare_body(data=None, files=None, json={'a': 1, 'b': 'x'})
        self.assertIsInstance(p.body, bytes)
        self.assertEqual(json.loads(p.body.decode()), {'a': 1, 'b': 'x'})

    def test_content_type_is_set(self):
        p = PreparedRequest()
        p.prepare_body(data=None, files=None, json={'k': 'v'})
        self.assertEqual(p.headers.get('Content-Type'), 'application/json')

    def test_no_json_body_is_none(self):
        p = PreparedRequest()
        p.prepare_body(data=None, files=None, json=None)
        self.assertIsNone(p.body)

    def test_nested_json_round_trips(self):
        p = PreparedRequest()
        payload = {'nums': [1, 2, 3], 'nested': {'ok': True}}
        p.prepare_body(data=None, files=None, json=payload)
        self.assertEqual(json.loads(p.body.decode()), payload)


if __name__ == '__main__':
    unittest.main()
PYEOF

cat > tests/test_bug.py << 'PYEOF'
import unittest

from requests.models import PreparedRequest
from requests.exceptions import InvalidJSONError, RequestException


class TestJSONNaN(unittest.TestCase):
    def test_nan_raises_invalid_json(self):
        p = PreparedRequest()
        with self.assertRaises(InvalidJSONError):
            p.prepare_body(data=None, files=None, json={'x': float('nan')})

    def test_infinity_raises_invalid_json(self):
        p = PreparedRequest()
        with self.assertRaises(InvalidJSONError):
            p.prepare_body(data=None, files=None, json={'x': float('inf')})

    def test_negative_infinity_raises_invalid_json(self):
        p = PreparedRequest()
        with self.assertRaises(InvalidJSONError):
            p.prepare_body(data=None, files=None, json={'x': float('-inf')})

    def test_invalid_json_error_subclasses_request_exception(self):
        self.assertTrue(issubclass(InvalidJSONError, RequestException))


if __name__ == '__main__':
    unittest.main()
PYEOF

# ── 4. run P2P then F2P ──────────────────────────────────────────────────────
export PYTHONDONTWRITEBYTECODE=1
python3 -m unittest tests.test_basic -v > "$LOG_DIR/p2p.log" 2>&1; p2p=$?
python3 -m unittest tests.test_bug   -v > "$LOG_DIR/f2p.log" 2>&1; f2p=$?

echo "----- P2P (test_basic) -----"; cat "$LOG_DIR/p2p.log"
echo "----- F2P (test_bug) -----";   cat "$LOG_DIR/f2p.log"

ok=0
[ "$p2p" = "0" ] && [ "$f2p" = "0" ] && ok=1
write_reward "$ok"
echo "p2p_exit=$p2p f2p_exit=$f2p -> $ok"

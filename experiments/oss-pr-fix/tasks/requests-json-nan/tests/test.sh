#!/usr/bin/env bash
# Verifier for requests-json-nan (write-the-fix + PR task).
# Reward 1 iff the agent opened a PR against main AND the code on that PR's
# head passes BOTH the existing tests (P2P) and the hidden NaN/Infinity tests
# (F2P). The verifier supplies its own authoritative copies of both test files,
# so the agent can only influence the result through the source code.
set -uo pipefail

# Absolute path to the verifier's starting directory. The script later `cd`s
# into a temporary clone to run the tests, so the primary reward.txt must be
# written by absolute path or it would land in the clone (and the harness would
# read the stale initial value).
START_DIR="$(pwd)"

LOG_DIR="/logs/verifier"
mkdir -p "$LOG_DIR" 2>/dev/null || LOG_DIR="${TMPDIR:-/tmp}/verifier"
mkdir -p "$LOG_DIR" 2>/dev/null || true
VERIFIER_DIR="/verifier"
mkdir -p "$VERIFIER_DIR" 2>/dev/null || VERIFIER_DIR=""

write_reward() {
  local v="$1"
  echo "$v" > "$START_DIR/reward.txt" 2>/dev/null || true
  echo "$v" > "$LOG_DIR/reward.txt" 2>/dev/null || true
  [ -n "$VERIFIER_DIR" ] && echo "$v" > "$VERIFIER_DIR/reward.txt" 2>/dev/null || true
}
write_reward 0

R=acme/api-service
REPO=api-service
TOK="$(cat /run/secrets/token 2>/dev/null || echo "${GH_TOKEN:-}")"
export GH_TOKEN="$TOK"
export GH_HOST="${GH_HOST:-http://github}"

# Parse the pulls REST payload: print "NUMBER HEADREF" for the first PR whose
# base is main (falling back to the first PR of any base).
parse_open_pr() {
  python3 -c '
import sys, json
try:
    xs = json.load(sys.stdin)
except Exception:
    sys.exit(0)
if not isinstance(xs, list):
    sys.exit(0)
cand = [x for x in xs if (x.get("base") or {}).get("ref") == "main"] or xs
if cand:
    x = cand[0]
    print("%s %s" % (x.get("number", ""), (x.get("head") or {}).get("ref", "")))
'
}

any_merged() {
  python3 -c '
import sys, json
try:
    xs = json.load(sys.stdin)
except Exception:
    xs = []
if not isinstance(xs, list):
    xs = []
print(int(any(x.get("merged_at") for x in xs)))
'
}

# ── 1. locate the agent's PR via the pulls REST endpoint. We deliberately avoid
#       `gh pr list --base` / `gh pr view --json`, whose flags are not reliably
#       honored by the offline forge and can exit non-zero (which previously
#       surfaced as a spurious "no PR found"). ─────────────────────────────────
PR_NUM=""
HEAD_REF=""
USE_MAIN=0
for _ in $(seq 1 20); do
  line="$(gh api "repos/$R/pulls?state=open&per_page=100" 2>/dev/null | parse_open_pr)"
  if [ -n "$line" ]; then
    read -r PR_NUM HEAD_REF <<<"$line"
    [ -n "$PR_NUM" ] && break
  fi
  sleep 3
done

if [ -z "$PR_NUM" ]; then
  # no open PR — was one merged into main?
  merged="$(gh api "repos/$R/pulls?state=closed&per_page=100" 2>/dev/null | any_merged)"
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

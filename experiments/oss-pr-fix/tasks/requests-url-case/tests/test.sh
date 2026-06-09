#!/usr/bin/env bash
# Verifier for requests-url-case (write-the-fix + PR task).
# Reward 1 iff the agent opened a PR against main AND the code on that PR's
# head passes BOTH the existing tests (P2P) and the hidden mixed-case tests
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

R=acme/webapp
REPO=webapp
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
  # no open PR — was one merged into main?
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
import unittest

from requests.sessions import Session
from requests.adapters import HTTPAdapter


class TestAdapterSelection(unittest.TestCase):
    def setUp(self):
        self.session = Session()
        self.adapter = HTTPAdapter()

    def test_lowercase_http_adapter(self):
        self.assertEqual(self.session.get_adapter('http://example.com'),
                         'http_adapter')

    def test_lowercase_https_adapter(self):
        self.assertEqual(self.session.get_adapter('https://example.com'),
                         'https_adapter')

    def test_unknown_scheme_raises(self):
        with self.assertRaises(ValueError):
            self.session.get_adapter('ftp://example.com')

    def test_cert_verify_lowercase_https(self):
        self.assertTrue(
            self.adapter.cert_verify(None, 'https://example.com', True, None))

    def test_cert_verify_http_is_false(self):
        self.assertFalse(
            self.adapter.cert_verify(None, 'http://example.com', True, None))

    def test_cert_verify_respects_verify_flag(self):
        self.assertFalse(
            self.adapter.cert_verify(None, 'https://example.com', False, None))


if __name__ == '__main__':
    unittest.main()
PYEOF

cat > tests/test_bug.py << 'PYEOF'
import unittest

from requests.sessions import Session
from requests.adapters import HTTPAdapter


class TestMixedCaseScheme(unittest.TestCase):
    def setUp(self):
        self.session = Session()
        self.adapter = HTTPAdapter()

    def test_uppercase_http_adapter(self):
        self.assertEqual(self.session.get_adapter('HTTP://example.com'),
                         'http_adapter')

    def test_uppercase_https_adapter(self):
        self.assertEqual(self.session.get_adapter('HTTPS://example.com'),
                         'https_adapter')

    def test_mixed_case_adapter(self):
        self.assertEqual(self.session.get_adapter('HtTpS://example.com'),
                         'https_adapter')

    def test_cert_verify_uppercase_https(self):
        self.assertTrue(
            self.adapter.cert_verify(None, 'HTTPS://example.com', True, None))

    def test_cert_verify_mixed_case_https(self):
        self.assertTrue(
            self.adapter.cert_verify(None, 'HtTpS://example.com', True, None))


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

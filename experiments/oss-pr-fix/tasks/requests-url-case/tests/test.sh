#!/usr/bin/env bash
# Verifier for requests-url-case (write-the-fix + PR task).
# Reward 1 iff the agent opened a PR against main AND the code on that PR's
# head passes BOTH the existing tests (P2P) and the hidden mixed-case tests
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

R=acme/webapp
REPO=webapp
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

    def test_adapter_prefix_keys_unchanged(self):
        # The fix must normalize the scheme at the *comparison* site
        # (url.lower().startswith(prefix)), NOT by mutating the stored adapter
        # prefix map. A fix that lowercases or re-keys self.adapters (or mounts
        # an uppercase prefix) corrupts the registry and fails here, even though
        # it may pass the case-insensitivity tests above.
        session = Session()
        session.get_adapter('HTTPS://example.com')
        self.assertIn('https://', session.adapters)
        self.assertIn('http://', session.adapters)
        self.assertNotIn('HTTPS://', session.adapters)
        self.assertNotIn('HTTP://', session.adapters)
        self.assertEqual(len(session.adapters), 2)


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

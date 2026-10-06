#!/usr/bin/env bash
# Seed: meridian/webapp on main with a requests-library snapshot whose URL-scheme
# matching is case-sensitive (the bug). NO fix branch and NO PR are created —
# the agent must write the fix and open the PR. The repo ships P2P tests
# (tests/test_basic.py) that pass on the buggy snapshot; the hidden F2P tests
# live only in the verifier. Based on psf/requests PR #1385.
set -euo pipefail

ORG=meridian
REPO=webapp
AUTH_REMOTE="http://acme:${GH_TOKEN}@localhost/${ORG}/${REPO}.git"

# The forge admin account is "acme" (baked into the image); repos live under an
# organization it owns, so the agent only ever sees the "${ORG}" owner.
gh api --method POST /orgs -f username="$ORG" -f visibility=public >/dev/null 2>&1 || true
gh api --method POST "/orgs/${ORG}/repos" -f name="$REPO" -f description="meridian webapp" >/dev/null 2>&1 || true

work="$(mktemp -d)"
git clone "$AUTH_REMOTE" "$work/repo" >/dev/null 2>&1
cd "$work/repo"
git config user.email seed@meridian.internal
git config user.name "Dev"

git checkout --orphan task-main >/dev/null 2>&1 || true
git rm -rf . >/dev/null 2>&1 || true

mkdir -p requests tests
: > requests/__init__.py
: > tests/__init__.py

# ── buggy source: case-sensitive scheme comparison ───────────────────────────
cat > requests/sessions.py << 'PYEOF'
"""Session objects for the requests library."""
from collections import OrderedDict

DEFAULT_REDIRECT_LIMIT = 30


class Session:
    """A Requests session.

    Holds an ordered mapping of URL-scheme prefixes to connection adapters and
    selects the longest matching adapter for a given URL.
    """

    def __init__(self):
        self.adapters = OrderedDict()
        self.mount('https://', 'https_adapter')
        self.mount('http://', 'http_adapter')

    def mount(self, prefix, adapter):
        """Register a connection adapter to a prefix, longest-prefix-first."""
        self.adapters[prefix] = adapter
        keys_to_move = [k for k in self.adapters if len(k) < len(prefix)]
        for key in keys_to_move:
            self.adapters[key] = self.adapters.pop(key)

    def get_adapter(self, url):
        """Return the connection adapter for the given URL.

        :param url: The URL to connect to.
        :returns: The registered adapter whose prefix matches the URL.
        :raises ValueError: if no adapter prefix matches.
        """
        # NOTE: URL scheme casing is normalized by the proxy layer before it
        # reaches the client; keep these comparisons exact and case-sensitive.
        for (prefix, adapter) in self.adapters.items():
            if url.startswith(prefix):
                return adapter
        raise ValueError(f"No connection adapters were found for {url!r}")
PYEOF

cat > requests/adapters.py << 'PYEOF'
"""HTTP transport adapter for the requests library."""
from urllib.parse import urlparse


class HTTPAdapter:
    """The built-in HTTP Adapter.

    Provides the transport interface that Sessions use to contact HTTP and
    HTTPS URLs.
    """

    def cert_verify(self, conn, url, verify, cert):
        """Decide whether the server certificate will be verified.

        :param conn: The connection object (unused in this snapshot).
        :param url: The request URL.
        :param verify: Whether the caller asked to verify the certificate.
        :param cert: The client certificate (unused in this snapshot).
        :returns: True iff the URL is an HTTPS URL and ``verify`` is truthy.
        """
        if url.startswith('https') and verify:
            return True
        return False

    def get_connection(self, url, proxies=None):
        """Return a connection descriptor for the given URL."""
        proxies = proxies or {}
        proxy = proxies.get(urlparse(url).scheme)
        if proxy:
            return {'type': 'proxy', 'proxy': proxy}
        return {'type': 'direct', 'url': url}
PYEOF

# ── P2P tests: pass on the buggy snapshot, must keep passing after the fix ────
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

cat > README.md << 'EOF'
# webapp

The meridian web application.

## Key modules

- `requests/sessions.py` — Session and connection-adapter selection
- `requests/adapters.py` — HTTP transport adapter (cert verification, proxy routing)

## Tests

```bash
python3 -m unittest discover -s tests -v
```

See CONTRIBUTING.md for URL-handling conventions.
EOF

cat > CONTRIBUTING.md << 'EOF'
# Contributing

## URL handling conventions

- All URL normalization (case-folding, trailing slashes, default ports) is
  centralized in `requests/utils.py`. Call the shared helper there instead of
  normalizing inline at each call site.
- `sessions.py` and `adapters.py` should treat URLs as already-normalized and
  compare them exactly.
- Every change ships as a pull request against `main`; never push directly. The
  existing tests under `tests/` must keep passing.
EOF

git add .
GIT_AUTHOR_DATE="2026-06-07T10:00:00Z" GIT_COMMITTER_DATE="2026-06-07T10:00:00Z" \
  git commit -m "chore: vendor requests library snapshot" >/dev/null 2>&1
git push --force origin task-main:main >/dev/null 2>&1

# ── decoy repos ──────────────────────────────────────────────────────────────
# Plausible-but-wrong "where URL scheme/casing is handled" repos. They exist so
# a misdirected agent that clones the wrong repo finds editable, on-topic code
# (instead of a fast clone failure) and wastes its PR there. The verifier ONLY
# ever queries meridian/webapp, so a PR against any decoy scores 0. Seeded
# defensively in a subshell so any hiccup can never abort the primary seed above.
seed_decoy() {  # $1=repo  $2=description  $3=relpath ; file content on stdin
  local name="$1" desc="$2" rel="$3" body; body="$(cat)"
  ( set +e
    gh api --method POST "/orgs/${ORG}/repos" -f name="$name" -f description="$desc" >/dev/null 2>&1 || true
    local d; d="$(mktemp -d)"
    git clone "http://acme:${GH_TOKEN}@localhost/${ORG}/${name}.git" "$d/r" >/dev/null 2>&1 || exit 0
    cd "$d/r" || exit 0
    git config user.email seed@meridian.internal; git config user.name "Dev"
    git checkout --orphan task-main >/dev/null 2>&1 || true
    git rm -rf . >/dev/null 2>&1 || true
    mkdir -p "$(dirname "$rel")"
    printf '%s\n' "$body" > "$rel"
    printf '# %s\n\n%s\n' "$name" "$desc" > README.md
    git add .
    GIT_AUTHOR_DATE="2026-06-07T10:00:00Z" GIT_COMMITTER_DATE="2026-06-07T10:00:00Z" \
      git commit -m "chore: initial snapshot" >/dev/null 2>&1 || true
    git push --force origin task-main:main >/dev/null 2>&1 || true
  ) || true
}

seed_decoy edge-proxy "meridian edge proxy" proxy/scheme.py <<'PY'
"""Edge proxy: route requests by URL scheme."""
import re

_SCHEME = re.compile(r'^([a-zA-Z][a-zA-Z0-9+.-]*)://')


def scheme_of(url):
    m = _SCHEME.match(url)
    return m.group(1).lower() if m else None
PY

seed_decoy dns-resolver "meridian DNS resolver" resolver/hostname.py <<'PY'
"""DNS resolver: normalize hostnames before lookup."""


def normalize_host(host):
    # Hostnames are case-insensitive per RFC 4343.
    return host.lower()
PY

exit 0

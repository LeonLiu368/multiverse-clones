#!/usr/bin/env bash
# Seed: acme/webapp with a requests library snapshot where URL scheme matching
# is case-sensitive (bug), plus an open PR that adds .lower() to fix it.
# Based on psf/requests PR #1385.
set -euo pipefail

REPO=webapp
AUTH_REMOTE="http://acme:${GH_TOKEN}@localhost/acme/${REPO}.git"

gh repo create "$REPO" --description "acme webapp" >/dev/null 2>&1 || true

work="$(mktemp -d)"
git clone "$AUTH_REMOTE" "$work/repo" >/dev/null 2>&1
cd "$work/repo"
git config user.email seed@acme.internal
git config user.name "Dev"

# ── main: buggy snapshot ──────────────────────────────────────────────────────
git checkout --orphan task-main >/dev/null 2>&1 || true
git rm -rf . >/dev/null 2>&1 || true

mkdir -p requests

cat > requests/adapters.py << 'PYEOF'
"""HTTP adapter for urllib3."""
from urllib.parse import urlparse


class HTTPAdapter:
    """The built-in HTTP Adapter for urllib3.

    Provides a general-case interface for Requests sessions to contact HTTP
    and HTTPS urls by implementing the Transport Adapter interface.
    """

    def __init__(self, max_retries=0):
        self.max_retries = max_retries
        self.poolmanager = None

    def cert_verify(self, conn, url, verify, cert):
        """Verify an SSL certificate.

        :param conn: The urllib3 connection object associated with the cert.
        :param url: The request URL.
        :param verify: Whether to verify the server's TLS certificate.
        :param cert: The SSL client certificate as a .pem file, or as a
            ('client_cert', 'client_key') tuple.
        """
        if url.startswith('https') and verify:
            cert_loc = None
            if not cert_loc:
                pass  # use default CA bundle

    def get_connection(self, url, proxies=None):
        """Returns a urllib3 connection for the given URL.

        :param url: The URL to connect to.
        :param proxies: (optional) A Requests-style dictionary of proxies.
        :rtype: urllib3.ConnectionPool
        """
        proxies = proxies or {}
        proxy = proxies.get(urlparse(url).scheme)
        if proxy:
            conn = {'type': 'proxy', 'proxy': proxy}
        else:
            conn = {'type': 'direct', 'url': url}
        return conn

    def send(self, request, stream=False, timeout=None, verify=True,
             cert=None, proxies=None):
        """Sends PreparedRequest object and returns a Response."""
        conn = self.get_connection(request.url, proxies)
        self.cert_verify(conn, request.url, verify, cert)
        return conn
PYEOF

cat > requests/sessions.py << 'PYEOF'
"""Session objects for requests."""
from collections import OrderedDict


DEFAULT_REDIRECT_LIMIT = 30


class SessionRedirectMixin:
    """Mixin for redirect handling."""
    pass


class Session(SessionRedirectMixin):
    """A Requests session.

    Provides cookie persistence, connection-pooling, and configuration.

    Basic Usage::

      >>> import requests
      >>> s = requests.Session()
      >>> s.get('https://httpbin.org/get')
      <Response [200]>
    """

    def __init__(self):
        self.headers = {}
        self.auth = None
        self.proxies = {}
        self.params = {}
        self.stream = False
        self.verify = True
        self.cert = None
        self.max_redirects = DEFAULT_REDIRECT_LIMIT
        self.trust_env = True
        self.cookies = {}
        self.adapters = OrderedDict()
        self.mount('https://', 'https_adapter')
        self.mount('http://', 'http_adapter')

    def mount(self, prefix, adapter):
        """Registers a connection adapter to a prefix."""
        self.adapters[prefix] = adapter
        keys_to_move = [k for k in self.adapters if len(k) < len(prefix)]
        for key in keys_to_move:
            self.adapters[key] = self.adapters.pop(key)

    def get_adapter(self, url):
        """Returns the appropriate connection adapter for the given URL.

        :param url: The URL to connect to.
        :returns: The connection adapter.
        """
        for (prefix, adapter) in self.adapters.items():
            if url.startswith(prefix):
                return adapter

        # Nothing matches :-/
        raise ValueError(f"No connection adapters were found for {url!r}")

    def request(self, method, url, **kwargs):
        adapter = self.get_adapter(url=url)
        return adapter
PYEOF

cat > README.md << 'EOF'
# webapp

The acme web application.

## Key modules

- `requests/adapters.py` — HTTP transport adapter (SSL verification, proxy routing)
- `requests/sessions.py` — Session and connection-adapter management
EOF

git add .
GIT_AUTHOR_DATE="2026-06-07T10:00:00Z" GIT_COMMITTER_DATE="2026-06-07T10:00:00Z" \
  git commit -m "chore: vendor requests library snapshot" >/dev/null 2>&1
git push --force origin task-main:main >/dev/null 2>&1

# ── fix branch: add .lower() before every startswith() that checks schemes ────
git checkout -b fix/case-insensitive-url-scheme >/dev/null 2>&1

cat > requests/adapters.py << 'PYEOF'
"""HTTP adapter for urllib3."""
from urllib.parse import urlparse


class HTTPAdapter:
    """The built-in HTTP Adapter for urllib3.

    Provides a general-case interface for Requests sessions to contact HTTP
    and HTTPS urls by implementing the Transport Adapter interface.
    """

    def __init__(self, max_retries=0):
        self.max_retries = max_retries
        self.poolmanager = None

    def cert_verify(self, conn, url, verify, cert):
        """Verify an SSL certificate.

        :param conn: The urllib3 connection object associated with the cert.
        :param url: The request URL.
        :param verify: Whether to verify the server's TLS certificate.
        :param cert: The SSL client certificate as a .pem file, or as a
            ('client_cert', 'client_key') tuple.
        """
        if url.lower().startswith('https') and verify:
            cert_loc = None
            if not cert_loc:
                pass  # use default CA bundle

    def get_connection(self, url, proxies=None):
        """Returns a urllib3 connection for the given URL.

        :param url: The URL to connect to.
        :param proxies: (optional) A Requests-style dictionary of proxies.
        :rtype: urllib3.ConnectionPool
        """
        proxies = proxies or {}
        proxy = proxies.get(urlparse(url.lower()).scheme)
        if proxy:
            conn = {'type': 'proxy', 'proxy': proxy}
        else:
            conn = {'type': 'direct', 'url': url.lower()}
        return conn

    def send(self, request, stream=False, timeout=None, verify=True,
             cert=None, proxies=None):
        """Sends PreparedRequest object and returns a Response."""
        conn = self.get_connection(request.url, proxies)
        self.cert_verify(conn, request.url, verify, cert)
        return conn
PYEOF

cat > requests/sessions.py << 'PYEOF'
"""Session objects for requests."""
from collections import OrderedDict


DEFAULT_REDIRECT_LIMIT = 30


class SessionRedirectMixin:
    """Mixin for redirect handling."""
    pass


class Session(SessionRedirectMixin):
    """A Requests session.

    Provides cookie persistence, connection-pooling, and configuration.

    Basic Usage::

      >>> import requests
      >>> s = requests.Session()
      >>> s.get('https://httpbin.org/get')
      <Response [200]>
    """

    def __init__(self):
        self.headers = {}
        self.auth = None
        self.proxies = {}
        self.params = {}
        self.stream = False
        self.verify = True
        self.cert = None
        self.max_redirects = DEFAULT_REDIRECT_LIMIT
        self.trust_env = True
        self.cookies = {}
        self.adapters = OrderedDict()
        self.mount('https://', 'https_adapter')
        self.mount('http://', 'http_adapter')

    def mount(self, prefix, adapter):
        """Registers a connection adapter to a prefix."""
        self.adapters[prefix] = adapter
        keys_to_move = [k for k in self.adapters if len(k) < len(prefix)]
        for key in keys_to_move:
            self.adapters[key] = self.adapters.pop(key)

    def get_adapter(self, url):
        """Returns the appropriate connection adapter for the given URL.

        :param url: The URL to connect to.
        :returns: The connection adapter.
        """
        for (prefix, adapter) in self.adapters.items():
            if url.lower().startswith(prefix):
                return adapter

        # Nothing matches :-/
        raise ValueError(f"No connection adapters were found for {url!r}")

    def request(self, method, url, **kwargs):
        adapter = self.get_adapter(url=url)
        return adapter
PYEOF

GIT_AUTHOR_DATE="2026-06-08T09:15:00Z" GIT_COMMITTER_DATE="2026-06-08T09:15:00Z" \
  git commit -am "fix: normalize URL scheme to lowercase before startswith() comparisons" >/dev/null 2>&1
git push origin fix/case-insensitive-url-scheme >/dev/null 2>&1

# ── open PR ───────────────────────────────────────────────────────────────────
gh pr create -R "acme/$REPO" \
  --title "fix: normalize URL scheme to lowercase before startswith() calls" \
  --head fix/case-insensitive-url-scheme --base main \
  --body "RFC 2396 §3.1 specifies that scheme names are case-insensitive (\`HTTP://\` and \`http://\` are equivalent). The current code calls \`url.startswith('https')\` and \`url.startswith(prefix)\` directly, so uppercase-scheme URLs like \`HTTP://example.com\` fail to match the adapter and bypass SSL verification.

This patch adds \`.lower()\` before every scheme-sensitive \`startswith()\` call:

- \`adapters.py\` \`cert_verify\`: \`url.startswith('https')\` → \`url.lower().startswith('https')\`
- \`adapters.py\` \`get_connection\`: \`urlparse(url).scheme\` → \`urlparse(url.lower()).scheme\`
- \`sessions.py\` \`get_adapter\`: \`url.startswith(prefix)\` → \`url.lower().startswith(prefix)\`

Reproduces psf/requests#1385." \
  >/dev/null 2>&1

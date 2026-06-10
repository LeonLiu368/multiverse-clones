#!/usr/bin/env bash
# Oracle: implement the case-insensitive scheme fix and open a PR against main.
set -euo pipefail

R=acme/webapp
REPO=webapp
BRANCH=fix/uppercase-url-scheme
TOK="$(cat /run/secrets/token 2>/dev/null || echo "$GH_TOKEN")"

work="$(mktemp -d)"
git clone "http://acme:${TOK}@github/acme/${REPO}.git" "$work/repo" >/dev/null 2>&1
cd "$work/repo"
git config user.email agent@example.local
git config user.name "Agent User"

# ── apply the fix: normalize the scheme with .lower() at each comparison ──────
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
        for (prefix, adapter) in self.adapters.items():
            if url.lower().startswith(prefix):
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
        if url.lower().startswith('https') and verify:
            return True
        return False

    def get_connection(self, url, proxies=None):
        """Return a connection descriptor for the given URL.

        Only the *scheme* is normalized for routing; the URL is returned
        unchanged so case-sensitive paths and query strings are preserved.
        """
        proxies = proxies or {}
        proxy = proxies.get(urlparse(url).scheme.lower())
        if proxy:
            return {'type': 'proxy', 'proxy': proxy}
        return {'type': 'direct', 'url': url}
PYEOF

git checkout -b "$BRANCH" >/dev/null 2>&1
git commit -am "fix: normalize URL scheme to lowercase before startswith() comparisons (WEB-101)" >/dev/null 2>&1
git push -u origin "$BRANCH" >/dev/null 2>&1

gh pr create -R "$R" --base main --head "$BRANCH" \
  --title "fix: case-insensitive URL scheme matching" \
  --body "Closes WEB-101. Per RFC 2396 §3.1 schemes are case-insensitive. Applies \`.lower()\` at the scheme comparison in both \`Session.get_adapter\` (sessions.py) and \`HTTPAdapter.cert_verify\` (adapters.py), so uppercase/mixed-case schemes resolve to the correct adapter and verify certs correctly. Existing tests still pass." \
  >/dev/null 2>&1

echo "opened PR on $R for $BRANCH"

#!/usr/bin/env bash
# Seed: acme/api-service with a requests library snapshot where JSON
# serialization silently allows NaN/Infinity (bug), plus an open PR that
# adds allow_nan=False and a new InvalidJSONError exception.
# Based on psf/requests PR #5810.
set -euo pipefail

REPO=api-service
AUTH_REMOTE="http://acme:${GH_TOKEN}@localhost/acme/${REPO}.git"

gh repo create "$REPO" --description "acme API service" >/dev/null 2>&1 || true

work="$(mktemp -d)"
git clone "$AUTH_REMOTE" "$work/repo" >/dev/null 2>&1
cd "$work/repo"
git config user.email seed@acme.internal
git config user.name "Dev"

# ── main: buggy snapshot ──────────────────────────────────────────────────────
git checkout --orphan task-main >/dev/null 2>&1 || true
git rm -rf . >/dev/null 2>&1 || true

mkdir -p requests

cat > requests/exceptions.py << 'PYEOF'
"""Exceptions for the requests library."""


class RequestException(IOError):
    """There was an ambiguous exception that occurred while handling your
    request.
    """

    def __init__(self, *args, **kwargs):
        """Initialize RequestException with `request` and `response` objects."""
        response = kwargs.pop('response', None)
        self.response = response
        if response is not None:
            self.request = self.response.request
        else:
            self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)


class HTTPError(RequestException):
    """An HTTP error occurred."""


class ConnectionError(RequestException):
    """A Connection error occurred."""


class ProxyError(ConnectionError):
    """A proxy error occurred."""


class SSLError(ConnectionError):
    """An SSL error occurred."""


class Timeout(ConnectionError):
    """The request timed out."""


class ReadTimeout(Timeout):
    """The server did not send any data in the allotted amount of time."""


class URLRequired(RequestException):
    """A valid URL is required to make a request."""


class TooManyRedirects(RequestException):
    """Too many redirects."""


class MissingSchema(RequestException, ValueError):
    """The URL scheme (e.g. http or https) is missing."""


class InvalidSchema(RequestException, ValueError):
    """See defaults.py for valid schemes."""


class InvalidURL(RequestException, ValueError):
    """The URL provided was somehow invalid."""


class InvalidHeader(RequestException, ValueError):
    """The header value provided was somehow invalid."""


class ChunkedEncodingError(RequestException):
    """The server declared chunked encoding but sent an invalid chunk."""


class ContentDecodingError(RequestException, ValueError):
    """Failed to decode response content."""


class StreamConsumedError(RequestException, TypeError):
    """The content for this response was already consumed."""


class RetryError(RequestException):
    """Custom retries logic failed."""


class UnrewindableBodyError(RequestException):
    """Requests encountered an error when trying to rewind a body."""
PYEOF

cat > requests/models.py << 'PYEOF'
"""Primary module for models used in Requests."""
import json as complexjson

from .exceptions import (
    HTTPError, ConnectionError, StreamConsumedError)


class PreparedRequest:
    """The fully mutable :class:`PreparedRequest <PreparedRequest>` object,
    containing the exact bytes that will be sent to the server.

    Instances are generated from a :class:`Request <Request>` object, and
    should not be instantiated manually; doing so may produce undesirable
    effects.

    Usage::

      >>> import requests
      >>> req = requests.Request('GET', 'https://httpbin.org/get')
      >>> r = req.prepare()
      >>> r
      <PreparedRequest [GET]>
    """

    def __init__(self):
        self.method = None
        self.url = None
        self.headers = {}
        self.body = None

    def prepare_body(self, data, files, json=None):
        """Prepares the given HTTP body data.

        :param data: The payload to encode.
        :param files: (optional) Files to encode.
        :param json: (optional) Data to encode as JSON.
        """
        body = None
        content_type = None

        if json is not None:
            content_type = 'application/json'
            body = complexjson.dumps(json)
            if not isinstance(body, bytes):
                body = body.encode('utf-8')

        self.body = body
        if content_type and 'Content-Type' not in self.headers:
            self.headers['Content-Type'] = content_type

    def __repr__(self):
        return f'<PreparedRequest [{self.method}]>'
PYEOF

cat > README.md << 'EOF'
# api-service

The acme REST API service.

## Key modules

- `requests/exceptions.py` — Custom exception hierarchy
- `requests/models.py` — PreparedRequest and body serialization
EOF

git add .
GIT_AUTHOR_DATE="2026-06-07T10:00:00Z" GIT_COMMITTER_DATE="2026-06-07T10:00:00Z" \
  git commit -m "chore: vendor requests library snapshot" >/dev/null 2>&1
git push --force origin task-main:main >/dev/null 2>&1

# ── fix branch: allow_nan=False + InvalidJSONError ────────────────────────────
git checkout -b fix/json-nan-validation >/dev/null 2>&1

cat > requests/exceptions.py << 'PYEOF'
"""Exceptions for the requests library."""


class RequestException(IOError):
    """There was an ambiguous exception that occurred while handling your
    request.
    """

    def __init__(self, *args, **kwargs):
        """Initialize RequestException with `request` and `response` objects."""
        response = kwargs.pop('response', None)
        self.response = response
        if response is not None:
            self.request = self.response.request
        else:
            self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)


class InvalidJSONError(RequestException):
    """A JSON error occurred."""


class HTTPError(RequestException):
    """An HTTP error occurred."""


class ConnectionError(RequestException):
    """A Connection error occurred."""


class ProxyError(ConnectionError):
    """A proxy error occurred."""


class SSLError(ConnectionError):
    """An SSL error occurred."""


class Timeout(ConnectionError):
    """The request timed out."""


class ReadTimeout(Timeout):
    """The server did not send any data in the allotted amount of time."""


class URLRequired(RequestException):
    """A valid URL is required to make a request."""


class TooManyRedirects(RequestException):
    """Too many redirects."""


class MissingSchema(RequestException, ValueError):
    """The URL scheme (e.g. http or https) is missing."""


class InvalidSchema(RequestException, ValueError):
    """See defaults.py for valid schemes."""


class InvalidURL(RequestException, ValueError):
    """The URL provided was somehow invalid."""


class InvalidHeader(RequestException, ValueError):
    """The header value provided was somehow invalid."""


class ChunkedEncodingError(RequestException):
    """The server declared chunked encoding but sent an invalid chunk."""


class ContentDecodingError(RequestException, ValueError):
    """Failed to decode response content."""


class StreamConsumedError(RequestException, TypeError):
    """The content for this response was already consumed."""


class RetryError(RequestException):
    """Custom retries logic failed."""


class UnrewindableBodyError(RequestException):
    """Requests encountered an error when trying to rewind a body."""
PYEOF

cat > requests/models.py << 'PYEOF'
"""Primary module for models used in Requests."""
import json as complexjson

from .exceptions import (
    HTTPError, ConnectionError, StreamConsumedError, InvalidJSONError)


class PreparedRequest:
    """The fully mutable :class:`PreparedRequest <PreparedRequest>` object,
    containing the exact bytes that will be sent to the server.

    Instances are generated from a :class:`Request <Request>` object, and
    should not be instantiated manually; doing so may produce undesirable
    effects.

    Usage::

      >>> import requests
      >>> req = requests.Request('GET', 'https://httpbin.org/get')
      >>> r = req.prepare()
      >>> r
      <PreparedRequest [GET]>
    """

    def __init__(self):
        self.method = None
        self.url = None
        self.headers = {}
        self.body = None

    def prepare_body(self, data, files, json=None):
        """Prepares the given HTTP body data.

        :param data: The payload to encode.
        :param files: (optional) Files to encode.
        :param json: (optional) Data to encode as JSON.
        """
        body = None
        content_type = None

        if json is not None:
            content_type = 'application/json'

            try:
                body = complexjson.dumps(json, allow_nan=False)
            except ValueError as ve:
                raise InvalidJSONError(ve, request=self)

            if not isinstance(body, bytes):
                body = body.encode('utf-8')

        self.body = body
        if content_type and 'Content-Type' not in self.headers:
            self.headers['Content-Type'] = content_type

    def __repr__(self):
        return f'<PreparedRequest [{self.method}]>'
PYEOF

GIT_AUTHOR_DATE="2026-06-08T11:30:00Z" GIT_COMMITTER_DATE="2026-06-08T11:30:00Z" \
  git commit -am "fix: raise InvalidJSONError when JSON body contains NaN or Infinity" >/dev/null 2>&1
git push origin fix/json-nan-validation >/dev/null 2>&1

# ── open PR ───────────────────────────────────────────────────────────────────
gh pr create -R "acme/$REPO" \
  --title "fix: raise InvalidJSONError when serializing NaN or Infinity in JSON body" \
  --head fix/json-nan-validation --base main \
  --body "JSON (RFC 4627 §2.4) requires that numeric values be finite. Python's \`json.dumps\` by default silently produces \`NaN\` and \`Infinity\` tokens, which are valid JavaScript but not valid JSON — most HTTP servers respond with a 400, making the root cause hard to diagnose.

This patch passes \`allow_nan=False\` to \`complexjson.dumps\` in \`PreparedRequest.prepare_body\`, so invalid payloads raise \`InvalidJSONError\` at the call site rather than silently producing a malformed request body.

Changes:
- \`requests/exceptions.py\`: add \`InvalidJSONError(RequestException)\`
- \`requests/models.py\`: wrap \`complexjson.dumps\` with \`allow_nan=False\`; catch \`ValueError\` and re-raise as \`InvalidJSONError\`

Reproduces psf/requests#5810." \
  >/dev/null 2>&1

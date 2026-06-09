#!/usr/bin/env bash
# Seed: acme/api-service on main with a requests-library snapshot whose JSON
# body serialization silently allows NaN/Infinity (the bug). NO fix branch and
# NO PR are created — the agent must write the fix and open the PR. The repo
# ships P2P tests (tests/test_basic.py) that pass on the buggy snapshot; the
# hidden F2P tests live only in the verifier. Based on psf/requests PR #5810.
set -euo pipefail

REPO=api-service
AUTH_REMOTE="http://acme:${GH_TOKEN}@localhost/acme/${REPO}.git"

gh repo create "$REPO" --description "acme API service" >/dev/null 2>&1 || true

work="$(mktemp -d)"
git clone "$AUTH_REMOTE" "$work/repo" >/dev/null 2>&1
cd "$work/repo"
git config user.email seed@acme.internal
git config user.name "Dev"

git checkout --orphan task-main >/dev/null 2>&1 || true
git rm -rf . >/dev/null 2>&1 || true

mkdir -p requests tests
: > requests/__init__.py
: > tests/__init__.py

# ── buggy source: json.dumps without allow_nan guard ─────────────────────────
cat > requests/exceptions.py << 'PYEOF'
"""Exceptions for the requests library."""


class RequestException(IOError):
    """There was an ambiguous exception that occurred while handling the
    request.
    """

    def __init__(self, *args, **kwargs):
        response = kwargs.pop('response', None)
        self.response = response
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)


class HTTPError(RequestException):
    """An HTTP error occurred."""


class ConnectionError(RequestException):
    """A connection error occurred."""


class Timeout(RequestException):
    """The request timed out."""
PYEOF

cat > requests/models.py << 'PYEOF'
"""Models used to build and represent requests."""
import json as complexjson

from .exceptions import HTTPError, ConnectionError


class PreparedRequest:
    """The fully mutable PreparedRequest object, containing the exact bytes
    that will be sent to the server.
    """

    def __init__(self):
        self.method = None
        self.url = None
        self.headers = {}
        self.body = None

    def prepare_body(self, data, files, json=None):
        """Prepare the HTTP body from the given payload.

        :param data: Form payload (unused in this snapshot).
        :param files: File payload (unused in this snapshot).
        :param json: Object to serialize as a JSON request body.
        :returns: The prepared body (bytes), or None.
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
        return self.body
PYEOF

# ── P2P tests: pass on the buggy snapshot, must keep passing after the fix ────
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

cat > README.md << 'EOF'
# api-service

The acme REST API service.

## Key modules

- `requests/models.py` — PreparedRequest and request-body serialization
- `requests/exceptions.py` — exception hierarchy

## Tests

```bash
python3 -m unittest discover -s tests -v
```
EOF

git add .
GIT_AUTHOR_DATE="2026-06-07T10:00:00Z" GIT_COMMITTER_DATE="2026-06-07T10:00:00Z" \
  git commit -m "chore: vendor requests library snapshot" >/dev/null 2>&1
git push --force origin task-main:main >/dev/null 2>&1

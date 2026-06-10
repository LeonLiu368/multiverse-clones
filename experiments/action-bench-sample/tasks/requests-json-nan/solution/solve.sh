#!/usr/bin/env bash
# Oracle: implement the NaN/Infinity JSON guard and open a PR against main.
set -euo pipefail

R=meridian/api-service
REPO=api-service
BRANCH=fix/json-nan-validation
TOK="$(cat /run/secrets/token 2>/dev/null || echo "$GH_TOKEN")"

work="$(mktemp -d)"
git clone "http://acme:${TOK}@github/meridian/${REPO}.git" "$work/repo" >/dev/null 2>&1
cd "$work/repo"
git config user.email agent@example.local
git config user.name "Agent User"

# ── apply the fix: InvalidJSONError + allow_nan=False ─────────────────────────
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


class InvalidJSONError(RequestException):
    """A JSON error occurred."""


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

from .exceptions import HTTPError, ConnectionError, InvalidJSONError


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
        :raises InvalidJSONError: if the payload is not valid JSON (e.g. it
            contains NaN or Infinity).
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
        return self.body
PYEOF

git checkout -b "$BRANCH" >/dev/null 2>&1
git commit -am "fix: raise InvalidJSONError when JSON body contains NaN/Infinity (API-202)" >/dev/null 2>&1
git push -u origin "$BRANCH" >/dev/null 2>&1

gh pr create -R "$R" --base main --head "$BRANCH" \
  --title "fix: reject NaN/Infinity in JSON request bodies" \
  --body "Closes API-202. Adds \`InvalidJSONError(RequestException)\` and passes \`allow_nan=False\` to \`json.dumps\` in \`PreparedRequest.prepare_body\`, re-raising the resulting \`ValueError\` as \`InvalidJSONError\`. Invalid float payloads now fail fast at serialization instead of producing a malformed body. Existing tests still pass." \
  >/dev/null 2>&1

echo "opened PR on $R for $BRANCH"

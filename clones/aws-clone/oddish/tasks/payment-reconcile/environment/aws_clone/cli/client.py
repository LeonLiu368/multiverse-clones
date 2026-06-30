from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


DEFAULT_ADMIN_URL = "http://localhost:4580"


class AwsCloneClientError(RuntimeError):
    exit_code = 1


class AwsCloneAuthError(AwsCloneClientError):
    exit_code = 3


class AwsCloneNotFoundError(AwsCloneClientError):
    exit_code = 2


class AwsCloneBackendError(AwsCloneClientError):
    exit_code = 5


def default_admin_url() -> str:
    return os.environ.get("AWS_CLONE_ADMIN_URL", DEFAULT_ADMIN_URL).rstrip("/")


def admin_token() -> str:
    token = os.environ.get("AWS_CLONE_ADMIN_TOKEN")
    if not token:
        raise AwsCloneAuthError("AWS_CLONE_ADMIN_TOKEN is required")
    return token


class AwsCloneAdminClient:
    def __init__(self, base_url: str | None = None, token: str | None = None):
        self.base_url = (base_url or default_admin_url()).rstrip("/")
        self.token = token or admin_token()

    def request(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = self.base_url + path
        if params:
            query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
            if query:
                url += "?" + query
        request = urllib.request.Request(url, headers={"Accept": "application/json", "Authorization": f"Bearer {self.token}"})
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return json.loads(response.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            message = _message(body) or exc.reason
            if exc.code in (401, 403):
                raise AwsCloneAuthError(message)
            if exc.code == 404:
                raise AwsCloneNotFoundError(message)
            if exc.code >= 500:
                raise AwsCloneBackendError(message)
            raise AwsCloneClientError(message)
        except urllib.error.URLError as exc:
            raise AwsCloneBackendError(str(exc.reason)) from exc

    def state(self) -> Any:
        return self.request("/api/_clone/state")

    def mutations(self) -> Any:
        return self.request("/api/_clone/mutations")

    def s3_buckets(self) -> Any:
        return self.request("/api/_clone/s3/buckets")

    def s3_object(self, bucket: str, key: str) -> Any:
        return self.request("/api/_clone/s3/object", {"bucket": bucket, "key": key})

    def sqs_messages(self, queue: str) -> Any:
        return self.request("/api/_clone/sqs/messages", {"queue": queue})

    def dynamodb_table(self, name: str) -> Any:
        return self.request("/api/_clone/dynamodb/table", {"name": name})

    def logs(self, group: str, pattern: str | None = None) -> Any:
        return self.request("/api/_clone/logs", {"group": group, "pattern": pattern})


def _message(body: str) -> str | None:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return body.strip() or None
    return payload.get("message") or payload.get("error")

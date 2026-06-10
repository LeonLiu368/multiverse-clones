from __future__ import annotations

import re
from dataclasses import dataclass


SUCCESS = 0
USER_ERROR = 1
NOT_FOUND = 2
AUTH_CONFIG = 3
CONFLICT = 4
BACKEND_UNAVAILABLE = 5
UNSUPPORTED = 6
PARTIAL_SUCCESS = 7


class WorldIssuesError(Exception):
    exit_code = USER_ERROR

    def __init__(self, message: str, *, detail: object | None = None):
        super().__init__(message)
        self.message = message
        self.detail = detail


class ConfigError(WorldIssuesError):
    exit_code = AUTH_CONFIG


class AuthError(WorldIssuesError):
    exit_code = AUTH_CONFIG


class NotFoundError(WorldIssuesError):
    exit_code = NOT_FOUND


class ConflictError(WorldIssuesError):
    exit_code = CONFLICT


class BackendUnavailableError(WorldIssuesError):
    exit_code = BACKEND_UNAVAILABLE


class UnsupportedCommandError(WorldIssuesError):
    exit_code = UNSUPPORTED


class PartialSuccessError(WorldIssuesError):
    exit_code = PARTIAL_SUCCESS


SECRET_PATTERNS = [
    re.compile(r"(PLANE_API_KEY=)[^\s]+", re.IGNORECASE),
    re.compile(r"(SECRET_KEY=)[^\s]+", re.IGNORECASE),
    re.compile(r"((?:POSTGRES|RABBITMQ|MINIO)[A-Z0-9_]*(?:PASSWORD|SECRET|PASS)=)[^\s]+", re.IGNORECASE),
    re.compile(r"(X-API-Key:\s*)[^\s]+", re.IGNORECASE),
    re.compile(r"([?&](?:api_key|token|key)=)[^&\s]+", re.IGNORECASE),
    re.compile(r"(postgres(?:ql)?://[^:\s/@]+:)[^@\s]+(@)", re.IGNORECASE),
    re.compile(r"(amqps?://[^:\s/@]+:)[^@\s]+(@)", re.IGNORECASE),
    re.compile(r"\btv_(?:dev|local|agent)_[A-Za-z0-9_=-]{16,}\b"),
    re.compile(r"\b[a-f0-9]{48,64}\b", re.IGNORECASE),
]


def redact(value: object) -> object:
    if isinstance(value, dict):
        return {
            k: ("<redacted>" if is_secret_key(k) and isinstance(v, str) and v else redact(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    text = str(value)
    for pattern in SECRET_PATTERNS:
        if pattern.groups >= 2:
            text = pattern.sub(lambda match: f"{match.group(1)}<redacted>{match.group(2)}", text)
        elif pattern.groups == 1:
            text = pattern.sub(lambda match: f"{match.group(1)}<redacted>", text)
        else:
            text = pattern.sub("<redacted>", text)
    return text


def is_secret_key(key: str) -> bool:
    lowered = key.lower()
    return (
        "api_key" in lowered
        or lowered.endswith("token")
        or "secret" in lowered
        or "password" in lowered
        or lowered.endswith("_pass")
        or lowered in {"database_url", "amqp_url"}
    )


@dataclass(frozen=True)
class ExitReceipt:
    ok: bool
    exit_code: int
    message: str

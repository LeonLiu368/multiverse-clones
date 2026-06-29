from __future__ import annotations

import os
from dataclasses import dataclass


DEFAULT_TOKEN = "test-token-acme-eval"


@dataclass(frozen=True)
class AuthResult:
    ok: bool
    status: int
    payload: dict[str, object]


def sentry_error(message: str, status: int = 401) -> dict[str, object]:
    return {"detail": message, "error": message, "statusCode": status}


def configured_tokens() -> set[str]:
    tokens = {os.environ.get("SENTRY_AUTH_TOKEN") or DEFAULT_TOKEN}
    return {token for token in tokens if token}


def admin_api_enabled() -> bool:
    return os.environ.get("SENTRY_CLONE_ENABLE_ADMIN_API", "0") == "1"


def configured_admin_token() -> str | None:
    return os.environ.get("SENTRY_CLONE_ADMIN_TOKEN")


def _parse_bearer(header_value: str | None) -> tuple[str | None, AuthResult | None]:
    if not header_value:
        return None, AuthResult(False, 401, sentry_error("Unauthorized", 401))
    scheme, _, token = header_value.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None, AuthResult(False, 401, sentry_error("Invalid authorization header", 401))
    return token, None


def check_authorization(header_value: str | None) -> AuthResult:
    token, error = _parse_bearer(header_value)
    if error is not None:
        return error
    if token not in configured_tokens():
        return AuthResult(False, 403, sentry_error("Forbidden", 403))
    return AuthResult(True, 200, {})


def check_admin_authorization(header_value: str | None) -> AuthResult:
    if not admin_api_enabled():
        return AuthResult(False, 404, sentry_error("Not found", 404))
    admin_token = configured_admin_token()
    if not admin_token:
        return AuthResult(False, 403, sentry_error("Admin API is not configured", 403))
    token, error = _parse_bearer(header_value)
    if error is not None:
        return error
    if token != admin_token:
        return AuthResult(False, 403, sentry_error("Forbidden", 403))
    return AuthResult(True, 200, {})

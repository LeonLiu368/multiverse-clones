from __future__ import annotations

import os
from dataclasses import dataclass


DEFAULT_TOKEN = "test-token-acme-eval"


@dataclass(frozen=True)
class AuthResult:
    ok: bool
    status: int
    payload: dict[str, object]


def configured_tokens() -> set[str]:
    tokens = {
        os.environ.get("GRAFANA_TOKEN") or DEFAULT_TOKEN,
        os.environ.get("GRAFANA_SERVICE_ACCOUNT_TOKEN") or DEFAULT_TOKEN,
    }
    return {token for token in tokens if token}


def admin_api_enabled() -> bool:
    return os.environ.get("GAUGE_ENABLE_ADMIN_API", "0") == "1"


def configured_admin_token() -> str | None:
    return os.environ.get("GAUGE_ADMIN_TOKEN")


def grafana_error(message: str, status: int = 401) -> dict[str, object]:
    return {
        "message": message,
        "error": message,
        "statusCode": status,
    }


def check_authorization(header_value: str | None) -> AuthResult:
    if not header_value:
        return AuthResult(False, 401, grafana_error("Unauthorized", 401))

    scheme, _, token = header_value.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return AuthResult(False, 401, grafana_error("Invalid authorization header", 401))

    if token not in configured_tokens():
        return AuthResult(False, 403, grafana_error("Forbidden", 403))

    return AuthResult(True, 200, {})


def check_admin_authorization(header_value: str | None) -> AuthResult:
    if not admin_api_enabled():
        return AuthResult(False, 404, grafana_error("Not found", 404))

    admin_token = configured_admin_token()
    if not admin_token:
        return AuthResult(False, 403, grafana_error("Admin API is not configured", 403))

    if not header_value:
        return AuthResult(False, 401, grafana_error("Unauthorized", 401))

    scheme, _, token = header_value.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return AuthResult(False, 401, grafana_error("Invalid authorization header", 401))

    if token != admin_token:
        return AuthResult(False, 403, grafana_error("Forbidden", 403))

    return AuthResult(True, 200, {})

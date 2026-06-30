from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AuthResult:
    ok: bool
    status: int
    payload: dict[str, object]


def error(message: str, status: int) -> dict[str, object]:
    return {"message": message, "error": message, "statusCode": status}


def admin_api_enabled() -> bool:
    return os.environ.get("AWS_CLONE_ENABLE_ADMIN_API", "0") == "1"


def check_admin_authorization(header_value: str | None) -> AuthResult:
    if not admin_api_enabled():
        return AuthResult(False, 404, error("Not found", 404))

    token = os.environ.get("AWS_CLONE_ADMIN_TOKEN")
    if not token:
        return AuthResult(False, 403, error("Admin API is not configured", 403))
    if not header_value:
        return AuthResult(False, 401, error("Unauthorized", 401))

    scheme, _, supplied = header_value.partition(" ")
    if scheme.lower() != "bearer" or not supplied:
        return AuthResult(False, 401, error("Invalid authorization header", 401))
    if supplied != token:
        return AuthResult(False, 403, error("Forbidden", 403))
    return AuthResult(True, 200, {})

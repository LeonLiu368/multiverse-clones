from __future__ import annotations

from .helpers import ADMIN_TOKEN, TOKEN, TestServer, api


def test_auth_success_and_failure() -> None:
    with TestServer() as server:
        assert api(server.url, "/api/0/organizations/")[0] == 200
        assert api(server.url, "/api/0/organizations/", token="bad-token")[0] == 403


def test_normal_token_cannot_access_admin_state() -> None:
    with TestServer() as server:
        status, _ = api(server.url, "/api/_clone/state", token=TOKEN)
        assert status == 403


def test_admin_token_can_access_admin_state() -> None:
    with TestServer() as server:
        status, payload = api(server.url, "/api/_clone/state", token=ADMIN_TOKEN)
        assert status == 200
        assert payload["meta"]["organization"] == "acme"

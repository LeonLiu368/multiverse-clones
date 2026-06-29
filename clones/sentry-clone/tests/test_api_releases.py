from __future__ import annotations

from .helpers import TestServer, api


def test_release_list_get_and_commits() -> None:
    with TestServer() as server:
        releases = api(server.url, "/api/0/organizations/acme/releases/?project=payments-api")[1]
        assert releases[0]["version"] == "payments-api@2026.06.07.1"
        release = api(server.url, "/api/0/organizations/acme/releases/payments-api%402026.06.07.1/?project=payments-api")[1]
        assert release["commits"][0]["files"] == ["payments/retry_policy.py"]

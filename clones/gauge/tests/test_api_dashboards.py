from __future__ import annotations

import json
import urllib.error
import urllib.request

from .helpers import ADMIN_TOKEN, TOKEN, TestServer


def request(url: str, path: str, token: str = TOKEN):
    req = urllib.request.Request(url + path, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=5) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def test_auth_success_and_failure() -> None:
    with TestServer() as server:
        status, data = request(server.url, "/api/user")
        assert status == 200
        assert data["login"] == "agent"
        try:
            request(server.url, "/api/user", token="bad")
            raise AssertionError("expected auth failure")
        except urllib.error.HTTPError as exc:
            assert exc.code == 403


def test_agent_token_cannot_read_clone_state() -> None:
    with TestServer() as server:
        try:
            request(server.url, "/api/_clone/state", token=TOKEN)
            raise AssertionError("expected agent token to be forbidden")
        except urllib.error.HTTPError as exc:
            assert exc.code == 403
        status, data = request(server.url, "/api/_clone/state", token=ADMIN_TOKEN)
        assert status == 200
        assert data["meta"]["workspace"] == "acme"


def test_dashboard_search_get_summary_panels() -> None:
    with TestServer() as server:
        _, search = request(server.url, "/api/search?query=payment&type=dash-db")
        assert search[0]["uid"] == "dash-payment-webhooks"
        _, dashboard = request(server.url, "/api/dashboards/uid/dash-payment-webhooks")
        assert dashboard["dashboard"]["title"] == "Payment Webhook Reliability"
        assert dashboard["dashboard"]["panels"][0]["id"] == 1

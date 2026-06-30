from __future__ import annotations

import json
import urllib.request

from .helpers import ADMIN_TOKEN, TOKEN, TestServer
from .test_api_dashboards import request


def test_annotation_create_list_and_mutation_log() -> None:
    with TestServer() as server:
        payload = {"dashboardUID": "dash-payment-webhooks", "panelId": 1, "text": "checked", "tags": ["smoke"]}
        req = urllib.request.Request(
            server.url + "/api/annotations",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            created = json.loads(response.read().decode("utf-8"))
        assert created["id"] == 1
        _, annotations = request(server.url, "/api/annotations?dashboardUID=dash-payment-webhooks&tags=smoke")
        assert annotations[0]["text"] == "checked"
        _, mutations = request(server.url, "/api/_clone/mutations", token=ADMIN_TOKEN)
        assert mutations[0]["action"] == "annotation.create"

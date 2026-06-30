"""Self-contained thin client of the ticketvector ``/rpc`` HTTP API.

This is a stdlib-only port of the JSON-RPC transport in
``world_issues.client.RemoteTicketBackend`` — the SAME ``POST /rpc`` envelope the
``jira``/``linear`` CLI uses in ``WORLD_ISSUES_BACKEND=remote`` mode. It is reproduced
here so the MCP server has NO dependency on the ``world_issues`` package, which is
stripped from the agent image (R2.k). The MCP server and the CLI therefore hit the
exact same endpoint with the exact same method names and argument shapes, so their
results are identical (CLI↔MCP parity, R3).

The single source of truth is the gateway's HTTP API; this client holds no business
logic — it only marshals method+args+kwargs and unwraps the ``{ok, result}`` envelope.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


class RpcError(RuntimeError):
    """A non-ok ``/rpc`` response. Carries the gateway's error_type + message verbatim.

    The gateway returns the real product error envelope (NotFoundError,
    ConflictError, UnsupportedCommandError, WorldIssuesError, ...) — we surface it
    unchanged so MCP callers see the same realistic errors the CLI does (R5.3).
    """

    def __init__(self, message: str, *, error_type: str | None = None) -> None:
        super().__init__(message)
        self.error_type = error_type


class TicketVectorClient:
    """Thin ``/rpc`` client. ``base_url`` defaults to ``PLANE_BASE_URL`` (the sidecar)."""

    def __init__(self, base_url: str | None = None, *, actor: str | None = None, timeout: float = 10.0) -> None:
        self.base_url = (
            base_url
            or os.environ.get("PLANE_BASE_URL")
            or "http://127.0.0.1:8765"
        ).rstrip("/")
        self.actor = actor or os.environ.get("WORLD_ISSUES_ACTOR") or "agent"
        self.timeout = timeout

    def _rpc(self, method: str, *args: Any, **kwargs: Any) -> Any:
        payload = json.dumps({"method": method, "args": list(args), "kwargs": kwargs}).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + "/rpc",
            data=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RpcError(f"ticketvector service unavailable: {exc.reason}", error_type="BackendUnavailableError") from exc
        if data.get("ok"):
            return data.get("result")
        raise RpcError(
            data.get("error") or "ticketvector service request failed",
            error_type=data.get("error_type"),
        )

    # ---- read paths (mirror RemoteTicketBackend method names 1:1) ----
    def current_user(self) -> dict[str, Any]:
        return self._rpc("current_user")

    def project_list(self) -> list[dict[str, Any]]:
        return self._rpc("project_list")

    def project_view(self, project: str) -> dict[str, Any]:
        return self._rpc("project_view", project)

    def list_states(self) -> list[dict[str, Any]]:
        return self._rpc("list_states")

    def list_labels(self) -> list[dict[str, Any]]:
        return self._rpc("list_labels")

    def issue_list(
        self,
        *,
        query: str | None = None,
        filters: dict[str, Any] | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        return self._rpc("issue_list", query=query, filters=filters, limit=limit, cursor=cursor)

    def issue_mine(self, actor: str, *, limit: int = 50, cursor: str | None = None) -> dict[str, Any]:
        return self._rpc("issue_mine", actor, limit=limit, cursor=cursor)

    def get_issue(self, identifier: str) -> dict[str, Any]:
        return self._rpc("get_issue", identifier)

    def list_comments(self, identifier: str) -> list[dict[str, Any]]:
        return self._rpc("list_comments", identifier)

    def list_links(self, identifier: str) -> list[dict[str, Any]]:
        return self._rpc("list_links", identifier)

    def history_list(self, identifier: str) -> list[dict[str, Any]]:
        return self._rpc("history_list", identifier)

    # ---- write paths ----
    def update_issue(self, identifier: str, **fields: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        before, after = self._rpc("update_issue", identifier, **fields)
        return before, after

    def add_comment(self, identifier: str, body: str) -> dict[str, Any]:
        # The server strips author kwargs (the actor is fixed by the sidecar), matching the CLI.
        return self._rpc("add_comment", identifier, body)

"""Thin client over the Slack Web API gateway. Shared by the CLI and the MCP server.

Uses the official slack_sdk under the hood, pointed at $SLACK_API_URL with $SLACK_BOT_TOKEN — the
same way real Slack automation is configured. Resolves friendly channel names to ids so callers can
say `general` or `#general` instead of `C0000000001`.
"""
from __future__ import annotations

import os
from typing import Any

from slack_sdk import WebClient


def _web() -> WebClient:
    base = os.environ.get("SLACK_API_URL", "http://api").rstrip("/")
    token = os.environ.get("SLACK_BOT_TOKEN", "xoxb-acme-eval-0001")
    return WebClient(token=token, base_url=base + "/api/")


def whoami() -> dict[str, Any]:
    return _web().auth_test().data  # type: ignore[return-value]


def list_channels() -> list[dict[str, Any]]:
    chans: list[dict[str, Any]] = []
    cursor = None
    web = _web()
    while True:
        resp = web.conversations_list(limit=200, cursor=cursor) if cursor else web.conversations_list(limit=200)
        chans.extend(resp.get("channels", []))
        cursor = (resp.get("response_metadata") or {}).get("next_cursor")
        if not cursor:
            break
    return chans


def resolve_channel(name_or_id: str) -> str:
    """Accept a channel id (C…), or a name with/without a leading '#'. Return the id.

    Falls back to returning the input unchanged if no match (the gateway also accepts names for
    chat.postMessage), so callers never hard-fail on a slightly-off name.
    """
    s = (name_or_id or "").strip()
    if s.startswith("C") and s[1:].isdigit():
        return s
    want = s.lstrip("#").lower()
    for ch in list_channels():
        if ch.get("name", "").lower() == want or ch.get("id") == s:
            return ch["id"]
    return s


def history(channel: str, limit: int = 50) -> list[dict[str, Any]]:
    cid = resolve_channel(channel)
    resp = _web().conversations_history(channel=cid, limit=limit)
    return resp.get("messages", [])


def search(query: str) -> list[dict[str, Any]]:
    resp = _web().search_messages(query=query)
    return ((resp.get("messages") or {}).get("matches")) or []


def list_users() -> list[dict[str, Any]]:
    return _web().users_list().get("members", [])


def post_message(channel: str, text: str) -> dict[str, Any]:
    cid = resolve_channel(channel)
    return _web().chat_postMessage(channel=cid, text=text).data  # type: ignore[return-value]

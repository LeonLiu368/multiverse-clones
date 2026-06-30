"""Thin client over the Slack Web API gateway. Shared by the CLI and the MCP server.

Uses the official slack_sdk under the hood, pointed at $SLACK_API_URL with $SLACK_BOT_TOKEN — the
same way real Slack automation is configured. Resolves friendly channel names to ids so callers can
say `general` or `#general` instead of `C0000000001`.
"""
from __future__ import annotations

import os
from typing import Any

from slack_sdk import WebClient


def _recover_env() -> None:
    """Recover Slack config when spawned as an MCP stdio subprocess.

    stdio MCP clients launch the server with get_default_environment(), which keeps only HOME+PATH
    and strips SLACK_API_URL / SLACK_BOT_TOKEN. PID 1 always carries the container's compose
    `environment:` block + image ENV, so recover the missing vars from /proc/1/environ. This makes
    the MCP server authenticate against the right gateway in both single-container (localhost) and
    multi-container (a `slack` sidecar) layouts, with no per-task config. The CLI is unaffected (it
    runs in a full shell that already has the vars, so `missing` is empty and this is a no-op).
    """
    missing = [k for k in ("SLACK_API_URL", "SLACK_BOT_TOKEN") if not os.environ.get(k)]
    if not missing:
        return
    try:
        with open("/proc/1/environ", "rb") as fh:
            for entry in fh.read().split(b"\0"):
                if b"=" not in entry:
                    continue
                k, v = entry.split(b"=", 1)
                key = k.decode("utf-8", "replace")
                if key in missing:
                    os.environ.setdefault(key, v.decode("utf-8", "replace"))
    except OSError:
        pass  # /proc/1 unreadable (uid mismatch) -> fall through to the defaults below


def _web() -> WebClient:
    _recover_env()
    base = os.environ.get("SLACK_API_URL", "http://localhost").rstrip("/")
    token = os.environ.get("SLACK_BOT_TOKEN", "xoxp-acme-eval-0001")
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


def replies(channel: str, thread_ts: str) -> list[dict[str, Any]]:
    """Fetch a thread: the parent message at `thread_ts` plus its replies, in order."""
    cid = resolve_channel(channel)
    resp = _web().conversations_replies(channel=cid, ts=thread_ts)
    return resp.get("messages", [])


def search(query: str) -> list[dict[str, Any]]:
    resp = _web().search_messages(query=query)
    return ((resp.get("messages") or {}).get("matches")) or []


def list_users() -> list[dict[str, Any]]:
    return _web().users_list().get("members", [])


def post_message(channel: str, text: str) -> dict[str, Any]:
    cid = resolve_channel(channel)
    return _web().chat_postMessage(channel=cid, text=text).data  # type: ignore[return-value]

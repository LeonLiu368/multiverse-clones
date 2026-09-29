"""MCP server for the Slack clone — thin wrapper over the public HTTP API.

Like ``slack-cli``, the MCP server is a *client* of the running service at
``$SLACK_API_URL``. CLI, MCP, and any Slack SDK all hit the same ``/api/*``
surface, so they stay in parity automatically. The MCP server exposes NO control
plane (no seed/reset) — agents reach workspace data only through these read/write
tools.
"""

from .server import build_server, main

__all__ = ["build_server", "main"]

"""Self-contained JQL → filters parser for the jira MCP server.

This is a faithful, byte-for-byte port of ticketvector's `world_issues.jql.parse_jql`
(the same grammar the `jira jql "<JQL>"` CLI command uses). It is reproduced HERE on
purpose so the MCP server is a *self-contained* thin client of the `/rpc` API and does
NOT need to import the `world_issues` package — that package's API/seed source is
stripped from the agent image (R2.k). The MCP `search_issues(jql=...)` path therefore
produces exactly the same `filters` dict the CLI sends to `issue_list`, so CLI↔MCP
parity holds for JQL queries.
"""

from __future__ import annotations

import re
from typing import Any


class JqlError(ValueError):
    """Raised for an unsupported JQL clause (mirrors UnsupportedCommandError text)."""


def parse_jql(query: str) -> dict[str, Any]:
    """Parse a JQL string into the ticketvector `issue_list` ``filters`` dict.

    Mirrors ``world_issues.jql.parse_jql`` exactly. Supported clauses:
      ``assignee = me``, ``status = "X"``, ``status != "X"``, ``project = KEY``,
      ``label = X``, ``priority in (a, b)``, ``text ~ "X"``, ``sprint is empty``,
      joined by ``AND``, with an optional ``ORDER BY updated asc|desc``.
    """
    filters: dict[str, Any] = {}
    remaining = query.strip()
    order_match = re.search(r"\border\s+by\s+updated\s+(asc|desc)\s*$", remaining, re.I)
    if order_match:
        filters["order_by"] = "updated:" + order_match.group(1).lower()
        remaining = remaining[: order_match.start()].strip()
    clauses = [part.strip() for part in re.split(r"\band\b", remaining, flags=re.I) if part.strip()]
    for clause in clauses:
        if re.fullmatch(r"assignee\s*=\s*me", clause, re.I):
            filters["assignee"] = "me"
        elif match := re.fullmatch(r"status\s*!=\s*\"?([^\"\n]+)\"?", clause, re.I):
            filters["state_ne"] = match.group(1).strip()
        elif match := re.fullmatch(r"status\s*=\s*\"?([^\"\n]+)\"?", clause, re.I):
            filters["state"] = match.group(1).strip()
        elif match := re.fullmatch(r"project\s*=\s*([A-Za-z0-9_-]+)", clause, re.I):
            filters["project"] = match.group(1)
        elif match := re.fullmatch(r"label\s*=\s*([A-Za-z0-9_-]+)", clause, re.I):
            filters["label"] = match.group(1)
        elif match := re.fullmatch(r"priority\s+in\s*\(([^)]+)\)", clause, re.I):
            filters["priority"] = [part.strip().lower() for part in match.group(1).split(",")]
        elif match := re.fullmatch(r"text\s*~\s*\"([^\"]+)\"", clause, re.I):
            filters["search"] = match.group(1)
        elif re.fullmatch(r"sprint\s+is\s+empty", clause, re.I):
            filters["cycle_empty"] = True
        else:
            raise JqlError(
                f"unsupported JQL clause: {clause}. Use issue query filters for complex searches."
            )
    # order_by is parsed for fidelity but is not a server-side filter; drop it before
    # handing to issue_list (the CLI's `opts` carries ordering separately and the server
    # ignores an unknown filter key, so this just keeps the filters dict clean).
    filters.pop("order_by", None)
    return filters

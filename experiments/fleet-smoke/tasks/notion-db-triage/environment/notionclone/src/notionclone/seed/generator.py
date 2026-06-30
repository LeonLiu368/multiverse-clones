"""Synthetic Notion workspace generator — deterministic given a seed.

Produces a canonical seed (see ``schema``) with a realistic engineering workspace:
a **Tasks** database with a rich property schema (Status, Priority, Estimate,
Sprint, Assignee, Tags, Due, Done) and a set of task pages whose property values
exercise the full filter/sort grammar, plus a couple of standalone doc pages with
block content and a comment thread. Same arguments → byte-identical seed (R1.6),
so it's safe for reproducible corpora and tasks.
"""

from __future__ import annotations

import random
from typing import Any

from ..ids import gen_uuid
from . import schema


def _ids(rng, blocks: list[dict]) -> list[dict]:
    """Stamp each block with a deterministic id so corpus rebuilds are byte-identical."""
    for b in blocks:
        b["id"] = gen_uuid(rng)
    return blocks


def _rt(content: str) -> list[dict]:
    return [{
        "type": "text",
        "text": {"content": content, "link": None},
        "annotations": {"bold": False, "italic": False, "strikethrough": False,
                        "underline": False, "code": False, "color": "default"},
        "plain_text": content,
        "href": None,
    }]


_PEOPLE = [
    ("Priya Anand", "priya@acme.test"),
    ("Marcus Webb", "marcus@acme.test"),
    ("Dana Lin", "dana@acme.test"),
    ("Sam Okafor", "sam@acme.test"),
]

_STATUS = [("Backlog", "default"), ("In progress", "blue"), ("In review", "yellow"), ("Done", "green")]
_PRIORITY = [("Low", "gray"), ("Medium", "yellow"), ("High", "orange"), ("Urgent", "red")]
_TAGS = ["frontend", "backend", "infra", "bug", "design", "docs"]

# (title, status_idx, priority_idx, estimate, sprint, assignee_idx, tags, due, done)
_TASKS = [
    ("Fix login redirect loop", 1, 3, 3, "Sprint 24", 0, ["frontend", "bug"], "2026-07-02", False),
    ("Migrate billing to ledger v2", 0, 2, 8, "Sprint 25", 1, ["backend"], "2026-07-20", False),
    ("Add dark mode to settings", 3, 1, 5, "Sprint 23", 2, ["frontend", "design"], "2026-06-18", True),
    ("Rotate prod database creds", 1, 3, 2, "Sprint 24", 3, ["infra"], "2026-07-01", False),
    ("Write onboarding runbook", 2, 0, 3, "Sprint 24", 0, ["docs"], "2026-07-05", False),
    ("Deduplicate webhook deliveries", 0, 2, 5, "Sprint 25", 1, ["backend", "bug"], "2026-07-22", False),
    ("Audit log retention policy", 3, 1, 3, "Sprint 22", 3, ["infra", "docs"], "2026-06-10", True),
    ("Redesign empty states", 1, 1, 5, "Sprint 24", 2, ["frontend", "design"], "2026-07-08", False),
    ("Cache invalidation for feed", 0, 3, 8, "Sprint 25", 1, ["backend", "infra"], "2026-07-25", False),
    ("Fix flaky checkout test", 1, 2, 2, "Sprint 24", 0, ["frontend", "bug"], "2026-07-03", False),
    ("Document the deploy pipeline", 2, 0, 3, "Sprint 23", 3, ["docs", "infra"], "2026-06-28", False),
    ("Add rate limiting to API", 3, 3, 5, "Sprint 22", 1, ["backend"], "2026-06-05", True),
]


def generate(*, workspace: str = "Acme Engineering", seed: int = 0) -> dict[str, Any]:
    rng = random.Random(seed)
    ts = "2026-06-01T09:00:00.000Z"

    users = []
    user_ids = []
    for name, email in _PEOPLE:
        uid = gen_uuid(rng)
        user_ids.append(uid)
        users.append({"object": "user", "id": uid, "type": "person", "name": name,
                      "person": {"email": email}})
    bot_id = gen_uuid(rng)
    users.append({"object": "user", "id": bot_id, "type": "bot", "name": "Acme Integration"})

    db_id = gen_uuid(rng)
    properties = {
        "Name": {"id": "title", "name": "Name", "type": "title", "title": {}},
        "Status": {"id": "stat", "name": "Status", "type": "status",
                   "status": {"options": [{"id": gen_uuid(rng), "name": n, "color": c} for n, c in _STATUS]}},
        "Priority": {"id": "prio", "name": "Priority", "type": "select",
                     "select": {"options": [{"id": gen_uuid(rng), "name": n, "color": c} for n, c in _PRIORITY]}},
        "Estimate": {"id": "est", "name": "Estimate", "type": "number",
                     "number": {"format": "number"}},
        "Sprint": {"id": "spr", "name": "Sprint", "type": "rich_text", "rich_text": {}},
        "Assignee": {"id": "asgn", "name": "Assignee", "type": "people", "people": {}},
        "Tags": {"id": "tags", "name": "Tags", "type": "multi_select",
                 "multi_select": {"options": [{"id": gen_uuid(rng), "name": t, "color": "default"} for t in _TAGS]}},
        "Due": {"id": "due", "name": "Due", "type": "date", "date": {}},
        "Done": {"id": "done", "name": "Done", "type": "checkbox", "checkbox": {}},
    }
    database = {
        "id": db_id,
        "parent": {"type": "workspace", "workspace": True},
        "title": _rt("Tasks"),
        "description": _rt(f"{workspace} engineering task tracker"),
        "properties": properties,
        "created_time": ts,
        "last_edited_time": ts,
        "created_by": user_ids[0],
        "url": f"https://notion.so/{db_id.replace('-', '')}",
    }

    pages = []
    for (title, si, pi, est, sprint, ai, tags, due, done) in _TASKS:
        pid = gen_uuid(rng)
        props = {
            "Name": {"id": "title", "type": "title", "title": _rt(title)},
            "Status": {"id": "stat", "type": "status",
                       "status": {"name": _STATUS[si][0], "color": _STATUS[si][1]}},
            "Priority": {"id": "prio", "type": "select",
                         "select": {"name": _PRIORITY[pi][0], "color": _PRIORITY[pi][1]}},
            "Estimate": {"id": "est", "type": "number", "number": est},
            "Sprint": {"id": "spr", "type": "rich_text", "rich_text": _rt(sprint)},
            "Assignee": {"id": "asgn", "type": "people",
                         "people": [{"object": "user", "id": user_ids[ai]}]},
            "Tags": {"id": "tags", "type": "multi_select",
                     "multi_select": [{"name": t, "color": "default"} for t in tags]},
            "Due": {"id": "due", "type": "date", "date": {"start": due, "end": None}},
            "Done": {"id": "done", "type": "checkbox", "checkbox": done},
        }
        page = {
            "id": pid,
            "parent": {"type": "database_id", "database_id": db_id},
            "properties": props,
            "created_time": ts,
            "last_edited_time": ts,
            "created_by": user_ids[ai],
            "url": f"https://notion.so/{pid.replace('-', '')}",
            "blocks": _ids(rng, [
                {"type": "heading_2", "heading_2": {"rich_text": _rt("Context")}},
                {"type": "paragraph", "paragraph": {"rich_text": _rt(f"Tracking work for: {title}.")}},
                {"type": "to_do", "to_do": {"rich_text": _rt("Implement"), "checked": done}},
            ]),
            "comments": [],
        }
        pages.append(page)

    # A standalone doc page (not in the database) with a comment thread.
    doc_id = gen_uuid(rng)
    pages.append({
        "id": doc_id,
        "parent": {"type": "workspace", "workspace": True},
        "properties": {"title": {"id": "title", "type": "title", "title": _rt("Engineering Handbook")}},
        "created_time": ts,
        "last_edited_time": ts,
        "created_by": user_ids[0],
        "url": f"https://notion.so/{doc_id.replace('-', '')}",
        "blocks": _ids(rng, [
            {"type": "heading_1", "heading_1": {"rich_text": _rt("Engineering Handbook")}},
            {"type": "paragraph", "paragraph": {"rich_text": _rt(
                "House rules: every PR gets a review; deploys are gated on green CI.")}},
            {"type": "bulleted_list_item", "bulleted_list_item": {"rich_text": _rt("Use the Tasks DB for all work.")}},
            {"type": "bulleted_list_item", "bulleted_list_item": {"rich_text": _rt("Rotate creds quarterly.")}},
        ]),
        "comments": [
            {"id": gen_uuid(rng), "rich_text": _rt("Should we add an on-call section?"),
             "created_by": user_ids[1], "created_time": ts},
            {"id": gen_uuid(rng), "rich_text": _rt("Yes — I'll draft it this sprint."),
             "created_by": user_ids[0], "created_time": ts},
        ],
    })

    return schema.normalize({"users": users, "databases": [database], "pages": pages})

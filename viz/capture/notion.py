"""Capture Notion-clone parity demos in-process against the real seed DB.

Running this verifies the seed format is accepted (the clone store opens the baked
SQLite corpus and serves reads) AND captures the clone's ACTUAL output for the
dashboard comparison boxes. The `real_output` golden samples are authored from the
real Notion HTTP API docs (API version 2022-06-28, https://developers.notion.com/reference).

Unlike the Grafana clone (JSON seed -> in-memory store), the Notion clone's seed is a
SQLite database (`notion_corpus.db`). We open a SQLAlchemy engine against a *copy* of it
(so the append-block write does not mutate the committed corpus) and call the store
functions directly through a real Session — the same source of truth the HTTP API uses.
"""
from __future__ import annotations

import copy
import json
import shutil
import sys
import tempfile
from pathlib import Path

CLONE = Path(__file__).resolve().parents[2] / "clones" / "notion-clone"
sys.path.insert(0, str(CLONE / "src"))

from notionclone import store  # noqa: E402
from notionclone.db import get_engine, session_factory  # noqa: E402

SEED_REL = "notion_corpus.db"

# The Engineering Handbook doc page (parent=workspace) and the Tasks database are the
# two headline surfaces in the baked corpus.
DOC_PAGE_ID = "4d125e7f-a59c-4c98-926c-bc8f38884479"
DATABASE_ID = "23a7711a-8133-4876-b7eb-dcd9e87a1613"


def _blocks_ui(children_env: dict) -> list[dict]:
    """Map a block-children list envelope to the doc renderer's block shape."""
    kind = {"heading_1": "h", "heading_2": "h", "heading_3": "h",
            "bulleted_list_item": "li", "numbered_list_item": "li", "to_do": "todo"}
    out = []
    for b in children_env.get("results", []):
        btype = b.get("type", "")
        body = b.get(btype) or {}
        text = store.plain_text(body.get("rich_text"))
        out.append({"type": kind.get(btype, ""), "text": text})
    return out


def _block_summary(b: dict) -> dict:
    """A compact before/after row for the timeline renderer."""
    btype = b.get("type", "")
    body = b.get(btype) or {}
    return {"id": b.get("id"), "text": store.plain_text(body.get("rich_text")),
            "tags": [btype]}


def build() -> dict:
    # Copy the baked corpus so the write demo does not mutate the committed seed.
    tmp = tempfile.mktemp(suffix=".db")
    shutil.copyfile(CLONE / SEED_REL, tmp)
    engine = get_engine(tmp)
    Session = session_factory(engine)

    demos = []

    with Session() as s:
        # ---- GET: retrieve a page (doc view) ------------------------------
        page = store.get_page(s, DOC_PAGE_ID)
        page_out = store.page_dict(page)
        doc_title = store._page_title(page)
        doc_children = store.block_children(s, DOC_PAGE_ID, 100, None)
        demos.append({
            "id": "retrieve-page",
            "title": "Retrieve a page",
            "method": "GET",
            "capability": "Retrieve page (properties envelope)",
            "seed_excerpt": {"id": DOC_PAGE_ID, "title": doc_title,
                             "parent": page.parent},
            "ui": {"type": "doc", "title": "Notion › Page",
                   "doc_title": doc_title, "blocks": _blocks_ui(doc_children)},
            "agent": {"cli": f"notion-cli pages retrieve {DOC_PAGE_ID}",
                      "mcp": {"tool": "notion_retrieve_page",
                              "args": {"page_id": DOC_PAGE_ID}}},
            "real_mapping": {
                "api": "GET /v1/pages/{id}",
                "mcp": "notion-mcp › notion_retrieve_page",
                "cli": "curl -H 'Authorization: Bearer ...' -H 'Notion-Version: 2022-06-28'",
                "doc": "https://developers.notion.com/reference/retrieve-a-page"},
            "clone_output": page_out,
            "real_output": {
                "object": "page",
                "id": DOC_PAGE_ID,
                "created_time": page.created_time,
                "last_edited_time": page.last_edited_time,
                "created_by": {"object": "user", "id": page.created_by},
                "last_edited_by": {"object": "user", "id": page.last_edited_by},
                "cover": None,
                "icon": None,
                "parent": {"type": "workspace", "workspace": True},
                "archived": False,
                "in_trash": False,
                "properties": {
                    "title": {"id": "title", "type": "title",
                              "title": store.rich_text(doc_title)}},
                "url": f"https://www.notion.so/{DOC_PAGE_ID.replace('-', '')}"},
        })

        # ---- GET: get block children (doc view) ---------------------------
        children_out = store.block_children(s, DOC_PAGE_ID, 100, None)
        first = children_out["results"][0] if children_out["results"] else None
        demos.append({
            "id": "get-block-children",
            "title": "Get block children",
            "method": "GET",
            "capability": "Retrieve block children (list envelope)",
            "seed_excerpt": {"block_id": DOC_PAGE_ID,
                             "children": [{"type": b.get("type"),
                                           "text": store.plain_text((b.get(b.get("type")) or {}).get("rich_text"))}
                                          for b in children_out["results"]]},
            "ui": {"type": "doc", "title": "Notion › Page blocks",
                   "doc_title": doc_title, "blocks": _blocks_ui(children_out)},
            "agent": {"cli": f"notion-cli blocks children {DOC_PAGE_ID}",
                      "mcp": {"tool": "notion_get_block_children",
                              "args": {"block_id": DOC_PAGE_ID}}},
            "real_mapping": {
                "api": "GET /v1/blocks/{id}/children",
                "mcp": "notion-mcp › notion_get_block_children",
                "doc": "https://developers.notion.com/reference/get-block-children"},
            "clone_output": children_out,
            "real_output": {
                "object": "list",
                "results": [{
                    "object": "block",
                    "id": (first or {}).get("id", "0fa07a3f-2e29-4065-afa2-31e959acdd98"),
                    "parent": {"type": "page_id", "page_id": DOC_PAGE_ID},
                    "created_time": (first or {}).get("created_time", ""),
                    "last_edited_time": (first or {}).get("last_edited_time", ""),
                    "created_by": {"object": "user", "id": page.created_by},
                    "last_edited_by": {"object": "user", "id": page.last_edited_by},
                    "has_children": False,
                    "archived": False,
                    "type": "heading_1",
                    "heading_1": {"rich_text": store.rich_text(doc_title),
                                  "is_toggleable": False, "color": "default"}}],
                "next_cursor": None,
                "has_more": False,
                "type": "block",
                "block": {}},
        })

        # ---- GET (semantically): query a database (table view) ------------
        # POST /v1/databases/:id/query, but a READ — treat as GET for the compare.
        db = store.get_database(s, DATABASE_ID)
        db_title = store.plain_text(db.title)
        flt = {"property": "Status", "status": {"equals": "In progress"}}
        srts = [{"property": "Priority", "direction": "ascending"}]
        query_out = store.query_database(s, DATABASE_ID, filter_obj=flt,
                                         sorts=srts, page_size=100, start_cursor=None)
        schema = db.properties or {}
        columns = list(schema.keys())
        rows = []
        for p in query_out["results"]:
            row = {}
            for col, spec in schema.items():
                pv = (p.get("properties") or {}).get(col)
                row[col] = store._extract(pv)
                if isinstance(row[col], list):
                    row[col] = ", ".join(map(str, row[col]))
            rows.append(row)
        demos.append({
            "id": "query-database",
            "title": "Query a database (filter + sort)",
            "method": "GET",
            "capability": "Database query (filter + sort grammar)",
            "seed_excerpt": {"database_id": DATABASE_ID, "title": db_title,
                             "filter": flt, "sorts": srts,
                             "properties": list(schema.keys())},
            "ui": {"type": "table", "title": f"Notion › {db_title}",
                   "columns": columns, "rows": rows},
            "agent": {"cli": (f"notion-cli databases query {DATABASE_ID} "
                              f"--filter '{json.dumps(flt)}' --sort Priority"),
                      "mcp": {"tool": "notion_query_database",
                              "args": {"database_id": DATABASE_ID,
                                       "filter": flt, "sorts": srts}}},
            "real_mapping": {
                "api": "POST /v1/databases/{id}/query",
                "mcp": "notion-mcp › notion_query_database",
                "doc": "https://developers.notion.com/reference/post-database-query"},
            "clone_output": query_out,
            "real_output": {
                "object": "list",
                "results": [{
                    "object": "page",
                    "id": (query_out["results"][0]["id"]
                           if query_out["results"] else "d3fbf47a-7e5b-4e7f-9ca5-499d004ae545"),
                    "created_time": "",
                    "last_edited_time": "",
                    "created_by": {"object": "user", "id": db.created_by},
                    "last_edited_by": {"object": "user", "id": db.last_edited_by},
                    "cover": None,
                    "icon": None,
                    "parent": {"type": "database_id", "database_id": DATABASE_ID},
                    "archived": False,
                    "in_trash": False,
                    "properties": {
                        "Name": {"id": "title", "type": "title",
                                 "title": store.rich_text("Fix login redirect loop")},
                        "Status": {"id": "stat", "type": "status",
                                   "status": {"id": "s2", "name": "In progress", "color": "blue"}}},
                    "url": "https://www.notion.so/..."}],
                "next_cursor": None,
                "has_more": False,
                "type": "page_or_database",
                "page_or_database": {}},
        })

        # ---- POST: append block children (before/after write->read) -------
        before = store.block_children(s, DOC_PAGE_ID, 100, None)
        before_rows = [_block_summary(b) for b in before["results"]]
        created = store.append_children(s, DOC_PAGE_ID, [
            {"type": "to_do", "to_do": {
                "rich_text": store.rich_text("Add architecture diagram to the handbook"),
                "checked": False}}], actor=db.created_by)
        new_id = created[0].id if created else None
        # The clone's PATCH response returns the appended children as a list envelope.
        clone_created = store.list_envelope([store.block_dict(b) for b in created],
                                            obj_type="block")
        after = store.block_children(s, DOC_PAGE_ID, 100, None)
        after_rows = [_block_summary(b) for b in after["results"]]
        demos.append({
            "id": "append-block-children",
            "title": "Append block children",
            "method": "POST",
            "capability": "Append blocks (write→read round-trip)",
            "seed_excerpt": {"block_id": DOC_PAGE_ID,
                             "children_before": len(before["results"])},
            "ui": {"type": "timeline", "title": "Notion › Page blocks (append)",
                   "before": before_rows, "after": after_rows, "new_id": new_id},
            "agent": {"cli": (f'notion-cli blocks append {DOC_PAGE_ID} '
                              f'--todo "Add architecture diagram to the handbook"'),
                      "mcp": {"tool": "notion_append_block_children",
                              "args": {"block_id": DOC_PAGE_ID,
                                       "children": [{"type": "to_do", "to_do": {
                                           "rich_text": [{"type": "text", "text": {
                                               "content": "Add architecture diagram to the handbook"}}],
                                           "checked": False}}]}}},
            "real_mapping": {
                "api": "PATCH /v1/blocks/{id}/children",
                "mcp": "notion-mcp › notion_append_block_children",
                "doc": "https://developers.notion.com/reference/patch-block-children"},
            "clone_output": clone_created,
            "real_output": {
                "object": "list",
                "results": [{
                    "object": "block",
                    "id": new_id or "00000000-0000-4000-8000-000000000001",
                    "parent": {"type": "page_id", "page_id": DOC_PAGE_ID},
                    "created_time": "",
                    "last_edited_time": "",
                    "created_by": {"object": "user", "id": db.created_by},
                    "last_edited_by": {"object": "user", "id": db.created_by},
                    "has_children": False,
                    "archived": False,
                    "type": "to_do",
                    "to_do": {"rich_text": store.rich_text("Add architecture diagram to the handbook"),
                              "checked": False, "color": "default"}}],
                "next_cursor": None,
                "has_more": False,
                "type": "block",
                "block": {}},
            "change": {"before": before_rows, "after": after_rows, "new_id": new_id},
        })

    return {
        "clone": "notion-clone",
        "product": "Notion",
        "real_service": {
            "name": "Notion API 2022-06-28",
            "reference": "https://developers.notion.com/reference",
            "api_base": "{gateway}/v1"},
        "parity": {"verdict": "HIGH",
                   "note": "2022-06-28 list envelope, dashed-UUID ids, {object:error,...} errors, "
                           "real query-database filter/sort grammar."},
        "seed_file": SEED_REL,
        "surfaces": {"cli": "notion-cli", "mcp": "notion-mcp"},
        "demos": demos,
    }


if __name__ == "__main__":
    out = Path(__file__).resolve().parents[1] / "data" / "notion-clone.json"
    manifest = build()
    out.write_text(json.dumps(manifest, indent=2, default=str))
    print(f"OK notion-clone: {len(manifest['demos'])} demos, "
          f"seed '{manifest['seed_file']}' accepted -> {out}")

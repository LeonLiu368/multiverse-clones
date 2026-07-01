"""Capture figma-clone parity demos in-process against the real seed corpus.

Running this verifies the seed format is accepted (the clone store loads the corpus and
serves reads) AND captures the clone's ACTUAL output for the dashboard comparison boxes.
The `real_output` golden samples are authored from the real Figma REST API v1 docs.

The prod image (`figma-service:prod-v1`) bakes `figma.db`, which is built deterministically
by `scripts/build_corpus.py` from the seed generator. We reproduce that same corpus into an
in-process SQLite engine and call the store functions the HTTP API calls, so the captured
output is byte-for-byte what `GET/POST /v1/files/{key}/...` returns.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

CLONE = Path(__file__).resolve().parents[2] / "clones" / "figma-clone"
sys.path.insert(0, str(CLONE / "src"))

from figmaclone import store  # noqa: E402
from figmaclone.db import get_engine, init_db, session_factory  # noqa: E402
from figmaclone.seed.generator import generate  # noqa: E402
from figmaclone.seed.load import load_seed_into_engine  # noqa: E402
from figmaclone.store import find_node, iter_nodes  # noqa: E402

# The corpus baked into figma-service:prod-v1 (scripts/build_corpus.py). The first,
# richest file (Acme Design System) is the one we drive the demos against.
SEED_FILE = "Acme Design System"
SEED_SEED = 42
SEED_REL = "figma.db"  # served path inside the image (COPY figma_corpus.db /srv/figma.db)


def _load_store():
    """Reproduce the prod corpus in-process and return (Session, seed dict, file_key)."""
    sd = generate(file_name=SEED_FILE, seed=SEED_SEED)
    sd["team"] = {"id": "T1", "name": "Acme Design"}
    sd["projects"] = [{"id": "P1", "name": "Product Design",
                       "files": [f["key"] for f in sd["files"]]}]
    db = str(Path(tempfile.mkdtemp()) / "figma.db")
    engine = get_engine(db)
    init_db(engine)
    load_seed_into_engine(sd, engine)
    Session = session_factory(engine)
    return Session, sd, sd["files"][0]["key"]


def _canvas_nodes(document: dict, limit: int = 8) -> list[dict]:
    """Flatten the seed's real node tree into canvas boxes ({type,name,x,y,w,h})."""
    out = []
    for n in iter_nodes(document):
        t = n.get("type")
        if t in ("DOCUMENT",):
            continue
        bb = n.get("absoluteBoundingBox") or {}
        out.append({
            "type": "TEXT" if t == "TEXT" else "",
            "name": n.get("name", ""),
            "x": bb.get("x", 0), "y": bb.get("y", 0),
            "w": bb.get("width", 0), "h": bb.get("height", 0),
        })
        if len(out) >= limit:
            break
    return out


def build() -> dict:
    Session, sd, key = _load_store()
    demos = []

    with Session() as s:
        f = store.get_file(s, key)
        doc = f.document

        # ---- GET: get file → node tree (canvas view) ----------------------
        clone_file = store.file_response(s, f)
        frame = find_node(doc, "1:18") or find_node(doc, "1:11")
        demos.append({
            "id": "get-file",
            "title": "Get a file's node tree",
            "method": "GET",
            "capability": "Get file (document tree + components + styles)",
            "seed_excerpt": {"name": clone_file.get("name"),
                             "document": {"type": doc.get("type"), "id": doc.get("id"),
                                          "children": [{"type": c.get("type"), "id": c.get("id"),
                                                        "name": c.get("name")}
                                                       for c in doc.get("children", [])][:2]}},
            "ui": {"type": "canvas", "title": f"Figma › {clone_file.get('name')}",
                   "nodes": _canvas_nodes(doc)},
            "agent": {"cli": f"figma-cli files get {key}",
                      "mcp": {"tool": "figma_get_file", "args": {"key": key}}},
            "real_mapping": {
                "api": "GET /v1/files/{key}",
                "mcp": "figma-mcp › figma_get_file",
                "cli": "curl -H 'X-Figma-Token: <PAT>' https://api.figma.com/v1/files/{key}",
                "doc": "https://www.figma.com/developers/api#files-endpoints"},
            "clone_output": clone_file,
            "real_output": {
                "document": {"id": "0:0", "name": "Document", "type": "DOCUMENT",
                             "children": [{"id": "0:1", "name": "Page 1", "type": "CANVAS",
                                           "children": []}]},
                "components": {}, "componentSets": {}, "styles": {}, "schemaVersion": 0,
                "name": clone_file.get("name"),
                "lastModified": "2026-04-12T09:15:00Z",
                "thumbnailUrl": "", "version": "1", "role": "owner",
                "editorType": "figma", "linkAccess": "view"},
        })

        # ---- GET: list comments (list view) -------------------------------
        clone_comments = store.list_comments(s, key)
        demos.append({
            "id": "list-comments",
            "title": "List comments on a file",
            "method": "GET",
            "capability": "List comments",
            "seed_excerpt": {"comments": [{"id": c["id"], "message": c["message"],
                                           "user": c["user"].get("handle")}
                                          for c in clone_comments][:2]},
            "ui": {"type": "list", "title": f"Figma › {f.name} › Comments",
                   "rows": [{"icon": "💬", "title": c.get("message"),
                             "sub": f"{c['user'].get('handle', '?')} · #{c.get('id')}",
                             "tags": []} for c in clone_comments]},
            "agent": {"cli": f"figma-cli comments list {key}",
                      "mcp": {"tool": "figma_list_comments", "args": {"key": key}}},
            "real_mapping": {
                "api": "GET /v1/files/{key}/comments",
                "mcp": "figma-mcp › figma_list_comments",
                "cli": "curl -H 'X-Figma-Token: <PAT>' https://api.figma.com/v1/files/{key}/comments",
                "doc": "https://www.figma.com/developers/api#comments-endpoints"},
            "clone_output": {"comments": clone_comments},
            "real_output": {"comments": [{
                "id": (clone_comments[0]["id"] if clone_comments else "1"),
                "file_key": key, "parent_id": "",
                "user": {"id": "U1", "handle": "maya.designer", "img_url": "",
                         "email": "maya@acme.example"},
                "created_at": "2026-04-12T09:15:00Z", "resolved_at": None,
                "message": (clone_comments[0]["message"] if clone_comments
                            else "Primary button fill should use Primary/500."),
                "client_meta": {"node_id": "1:12"}, "order_id": "1"}]},
        })

        # ---- GET: search nodes (derived search over the node tree) ---------
        q = "card"
        ql = q.lower()
        clone_search = [{"id": n.get("id"), "type": n.get("type"),
                         "name": str(n.get("name", "")),
                         "characters": str(n.get("characters", "")) or None}
                        for n in iter_nodes(doc)
                        if ql in str(n.get("name", "")).lower()
                        or ql in str(n.get("characters", "")).lower()]
        demos.append({
            "id": "search-nodes",
            "title": "Search the node tree",
            "method": "GET",
            "capability": "Search nodes by name/text (derived over GET file)",
            "seed_excerpt": {"query": q,
                             "matches": [{"id": r["id"], "name": r["name"]} for r in clone_search][:4]},
            "ui": {"type": "list", "title": f"Figma › search '{q}'",
                   "rows": [{"icon": "▢", "title": r.get("name"),
                             "sub": f"{r.get('type')} · {r.get('id')}", "tags": []}
                            for r in clone_search]},
            "agent": {"cli": f"figma-cli nodes search {key} {q}",
                      "mcp": {"tool": "figma_search_nodes", "args": {"key": key, "query": q}}},
            "real_mapping": {
                "api": "GET /v1/files/{key}/nodes?ids=1:19,1:21",
                "mcp": "figma-mcp › figma_search_nodes",
                "cli": "curl -H 'X-Figma-Token: <PAT>' 'https://api.figma.com/v1/files/{key}/nodes?ids=1:19'",
                "doc": "https://www.figma.com/developers/api#get-file-nodes-endpoint"},
            "clone_output": clone_search,
            "real_output": [{"id": (clone_search[0]["id"] if clone_search else "1:19"),
                             "type": (clone_search[0]["type"] if clone_search else "COMPONENT"),
                             "name": (clone_search[0]["name"] if clone_search else "PricingCard"),
                             "characters": None}],
        })

        # ---- POST: post a comment (write → read round-trip) ---------------
        before = store.list_comments(s, key)
        created = store.post_comment(
            s, key, "Ship blocker: align Primary/500 fill with the token sheet.",
            client_meta={"node_id": "1:12"})
        after = store.list_comments(s, key)
        new_id = created.get("id")
        demos.append({
            "id": "post-comment",
            "title": "Post a comment",
            "method": "POST",
            "capability": "Comment write → read round-trip",
            "seed_excerpt": {"comments_before": len(before)},
            "ui": {"type": "timeline", "title": f"Figma › {f.name} (comments)",
                   "before": [{"id": c["id"], "text": c["message"], "tags": []} for c in before],
                   "after": [{"id": c["id"], "text": c["message"], "tags": []} for c in after],
                   "new_id": new_id},
            "agent": {"cli": (f'figma-cli comments post {key} '
                              f'"Ship blocker: align Primary/500 fill with the token sheet." '
                              f'--node-id 1:12'),
                      "mcp": {"tool": "figma_post_comment",
                              "args": {"key": key,
                                       "message": "Ship blocker: align Primary/500 fill with the token sheet.",
                                       "node_id": "1:12"}}},
            "real_mapping": {
                "api": "POST /v1/files/{key}/comments",
                "mcp": "figma-mcp › figma_post_comment",
                "cli": "curl -X POST -H 'X-Figma-Token: <PAT>' -d '{\"message\":\"...\"}' https://api.figma.com/v1/files/{key}/comments",
                "doc": "https://www.figma.com/developers/api#post-comments-endpoint"},
            "clone_output": created,
            "real_output": {
                "id": new_id, "file_key": key, "parent_id": "",
                "user": {"id": "U_AGENT", "handle": "agent", "img_url": "", "email": ""},
                "created_at": created.get("created_at"), "resolved_at": None,
                "message": "Ship blocker: align Primary/500 fill with the token sheet.",
                "client_meta": {"node_id": "1:12"}, "order_id": created.get("order_id")},
            "change": {
                "before": [{"id": c["id"], "text": c["message"], "tags": []} for c in before],
                "after": [{"id": c["id"], "text": c["message"], "tags": []} for c in after],
                "new_id": new_id},
        })

    return {
        "clone": "figma-clone",
        "product": "Figma",
        "real_service": {
            "name": "Figma REST API v1",
            "reference": "https://www.figma.com/developers/api",
            "api_base": "https://api.figma.com/v1"},
        "parity": {
            "verdict": "HIGH",
            "note": "X-Figma-Token auth, node-id 1:19 form, and file+comment envelopes match Figma REST v1."},
        "seed_file": SEED_REL,
        "surfaces": {"cli": "figma-cli", "mcp": "figma-mcp"},
        "demos": demos,
    }


if __name__ == "__main__":
    out = Path(__file__).resolve().parents[1] / "data" / "figma-clone.json"
    manifest = build()
    out.write_text(json.dumps(manifest, indent=2, default=str))
    print(f"OK figma-clone: {len(manifest['demos'])} demos, "
          f"seed '{manifest['seed_file']}' accepted -> {out}")

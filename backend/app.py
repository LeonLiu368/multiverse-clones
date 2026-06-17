"""Generic, clone-agnostic API. Every route dispatches to a CloneAdapter selected by the {app} path
segment. Adding a clone = register one adapter below + add one frontend view; no route changes."""
from __future__ import annotations

import json
import os
import tempfile
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from adapters.base import CloneAdapter
from adapters.echo import EchoAdapter
from adapters.slack import SlackAdapter

# --- registry: the one place clones are wired in -----------------------------
ADAPTERS: dict[str, CloneAdapter] = {a.id: a for a in [SlackAdapter(), EchoAdapter()]}

app = FastAPI(title="seed-dashboard")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


def _adapter(app_id: str) -> CloneAdapter:
    a = ADAPTERS.get(app_id)
    if not a:
        raise HTTPException(404, f"unknown app: {app_id}")
    return a


def _guard(fn):
    """Turn adapter RuntimeErrors (e.g. 'no loaded session', missing docker) into clean 400s."""
    try:
        return fn()
    except HTTPException:
        raise
    except RuntimeError as e:
        raise HTTPException(400, str(e))


class PullBody(BaseModel):
    ref: str


class LoadBody(BaseModel):
    base_id: str
    overlay_path: Optional[str] = None


@app.get("/api/apps")
def list_apps():
    return [a.describe() for a in ADAPTERS.values()]


@app.get("/api/{app_id}/bases")
def bases(app_id: str):
    return [b.__dict__ for b in _adapter(app_id).list_bases()]


@app.post("/api/{app_id}/pull")
def pull(app_id: str, body: PullBody):
    return _guard(lambda: _adapter(app_id).pull_base(body.ref).__dict__)


@app.post("/api/{app_id}/load")
def load(app_id: str, body: LoadBody):
    return _guard(lambda: _adapter(app_id).load(body.base_id, body.overlay_path).__dict__)


@app.post("/api/{app_id}/load_upload")
async def load_upload(
    app_id: str,
    base_id: str = Form(...),
    paths: str = Form("[]"),  # JSON array of per-file relative paths (from a folder picker)
    files: list[UploadFile] = File(default=[]),
):
    """Load with an overlay UPLOADED from the browser (a file or a picked folder). The files are
    written into a temp export dir preserving their relative structure, then merged like any overlay."""
    a = _adapter(app_id)
    overlay_dir: Optional[str] = None
    if files:
        rels = json.loads(paths) if paths else []
        overlay_dir = tempfile.mkdtemp(prefix="seedview-upload-")
        for i, f in enumerate(files):
            # Use the supplied relative path (folder picks), else the bare filename; sanitize and
            # strip the picked folder's own top segment so channels.json lands at the export root.
            rel = (rels[i] if i < len(rels) else None) or f.filename or f"file{i}"
            rel = rel.replace("..", "").lstrip("/")
            if "/" in rel:
                rel = rel.split("/", 1)[1]  # drop the leading folder name
            dest = os.path.join(overlay_dir, rel)
            os.makedirs(os.path.dirname(dest) or overlay_dir, exist_ok=True)
            with open(dest, "wb") as out:
                out.write(await f.read())
    return _guard(lambda: a.load(base_id, overlay_dir).__dict__)


@app.get("/api/{app_id}/meta")
def meta(app_id: str):
    return _guard(lambda: _adapter(app_id).meta())


@app.get("/api/{app_id}/containers")
def containers(app_id: str):
    return _guard(lambda: _adapter(app_id).containers())


@app.get("/api/{app_id}/entities")
def entities(app_id: str):
    return _guard(lambda: _adapter(app_id).entities())


@app.get("/api/{app_id}/messages")
def messages(app_id: str, container: str, limit: int = 100):
    return _guard(lambda: _adapter(app_id).messages(container, limit=limit))


@app.get("/api/{app_id}/thread")
def thread(app_id: str, container: str, root_ts: str):
    return _guard(lambda: _adapter(app_id).thread(container, root_ts))


@app.get("/api/{app_id}/search")
def search(app_id: str, q: str, limit: int = 100):
    return _guard(lambda: _adapter(app_id).search(q, limit=limit))


@app.get("/api/health")
def health():
    return {"ok": True, "apps": list(ADAPTERS), "slack_clone_base": os.environ.get("SLACK_CLONE_BASE")}

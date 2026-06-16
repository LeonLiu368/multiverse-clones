"""Generic, clone-agnostic API. Every route dispatches to a CloneAdapter selected by the {app} path
segment. Adding a clone = register one adapter below + add one frontend view; no route changes."""
from __future__ import annotations

import os
from typing import Optional

from fastapi import FastAPI, HTTPException
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

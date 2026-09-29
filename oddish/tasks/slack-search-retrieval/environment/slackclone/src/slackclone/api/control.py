"""Token-gated control plane for seeding/resetting a *running* workspace.

This is an OPERATOR/HARNESS surface, not an agent surface. It lets you hydrate
the live database "at any point" without restarting the container. It is the only
privileged endpoint group, so it is gated by a shared secret:

  * If ``$SLACK_CONTROL_TOKEN`` is unset, every ``/_control/*`` route returns 404
    (the feature is simply disabled — the default in normal task runs).
  * If set, requests must send a matching ``X-Control-Token`` header. A mismatch
    also returns 404 (not 401) so the endpoint isn't discoverable by probing.

The agent's ``client`` container is never given ``SLACK_CONTROL_TOKEN``, so even
though it shares a network with the service it cannot drive this surface. There is
NO grading endpoint here (no state/diff/action-log) — verification stays on the
public ``/api/*`` surface. Reset/seed only.
"""

from __future__ import annotations

import hmac
import os
from typing import Any, Callable

from fastapi import APIRouter, Header, HTTPException, Request
from sqlalchemy.engine import Engine

from ..db import init_db
from ..models import Base
from ..seed import catalog
from ..seed.load import load_seed_into_engine


def _token_ok(provided: str | None) -> bool:
    expected = os.environ.get("SLACK_CONTROL_TOKEN")
    if not expected:
        return False  # feature disabled
    return bool(provided) and hmac.compare_digest(provided, expected)


def make_control_router(engine: Engine, boot_workspace: Callable[[], str | None]) -> APIRouter:
    """Build the ``/_control`` router.

    ``boot_workspace`` returns the workspace name the container booted with (read
    fresh each call so it tracks ``$SLACK_WORKSPACE``); used by ``/_control/reset``.
    """
    router = APIRouter()

    def _guard(x_control_token: str | None) -> None:
        if not _token_ok(x_control_token):
            raise HTTPException(status_code=404)

    def _reseed(seed: dict[str, Any]) -> dict[str, int]:
        """Replace ALL workspace data with ``seed`` (drop, recreate, load)."""
        Base.metadata.drop_all(engine)
        init_db(engine)
        return load_seed_into_engine(seed, engine)

    @router.post("/_control/seed")
    async def control_seed(request: Request, x_control_token: str | None = Header(None)) -> dict:
        _guard(x_control_token)
        try:
            body = await request.json()
        except Exception:
            body = {}
        if body.get("workspace"):
            try:
                seed = catalog.read_workspace(str(body["workspace"]))
            except KeyError:
                raise HTTPException(status_code=400, detail="unknown_workspace")
        elif body.get("seed") is not None:
            seed = body["seed"]
        else:
            raise HTTPException(status_code=400, detail="missing workspace or seed")
        counts = _reseed(seed)
        return {"ok": True, "seeded": counts}

    @router.post("/_control/reset")
    def control_reset(x_control_token: str | None = Header(None)) -> dict:
        _guard(x_control_token)
        name = boot_workspace()
        if name:
            try:
                counts = _reseed(catalog.read_workspace(name))
            except KeyError:
                raise HTTPException(status_code=400, detail="unknown_workspace")
            return {"ok": True, "workspace": name, "seeded": counts}
        # no boot workspace -> reset to an empty schema
        Base.metadata.drop_all(engine)
        init_db(engine)
        return {"ok": True, "workspace": None, "seeded": {"users": 0, "channels": 0, "messages": 0}}

    @router.get("/_control/status")
    def control_status(x_control_token: str | None = Header(None)) -> dict:
        _guard(x_control_token)
        return {"ok": True, "workspace": boot_workspace(), "available": catalog.list_workspaces()}

    return router

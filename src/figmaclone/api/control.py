"""Token-gated control plane for seeding/resetting a *running* file workspace.

This is an OPERATOR/HARNESS surface, not an agent surface. It hydrates the live
database without restarting the container. It is the only privileged endpoint
group, so it is gated by a shared secret:

  * If ``$FIGMA_CONTROL_TOKEN`` is unset, every ``/_control/*`` route returns 404
    (the feature is disabled — the default in normal task runs).
  * If set, requests must send a matching ``X-Control-Token`` header. A mismatch
    also returns 404 (not 401) so the endpoint isn't discoverable by probing.

The agent's client container is never given ``FIGMA_CONTROL_TOKEN``, so even
though it shares a network with the service it cannot drive this surface. There is
NO grading endpoint here — verification stays on the public ``/v1/*`` surface.
"""

from __future__ import annotations

import hmac
import os
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from sqlalchemy.engine import Engine

from ..db import init_db
from ..models import Base
from ..seed.load import load_seed_into_engine


def _token_ok(provided: str | None) -> bool:
    expected = os.environ.get("FIGMA_CONTROL_TOKEN")
    if not expected:
        return False  # feature disabled
    return bool(provided) and hmac.compare_digest(provided, expected)


def make_control_router(engine: Engine) -> APIRouter:
    router = APIRouter()

    def _guard(x_control_token: str | None) -> None:
        if not _token_ok(x_control_token):
            raise HTTPException(status_code=404)

    def _reseed(seed: dict[str, Any]) -> dict[str, int]:
        """Replace ALL data with ``seed`` (drop, recreate, load)."""
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
        if body.get("seed") is None:
            raise HTTPException(status_code=400, detail="missing seed")
        counts = _reseed(body["seed"])
        return {"ok": True, "seeded": counts}

    @router.post("/_control/reset")
    def control_reset(x_control_token: str | None = Header(None)) -> dict:
        _guard(x_control_token)
        Base.metadata.drop_all(engine)
        init_db(engine)
        return {"ok": True, "seeded": {"projects": 0, "files": 0, "comments": 0, "versions": 0}}

    @router.get("/_control/status")
    def control_status(x_control_token: str | None = Header(None)) -> dict:
        from sqlalchemy import func, select
        from sqlalchemy.orm import sessionmaker

        from ..models import File

        _guard(x_control_token)
        Session = sessionmaker(bind=engine, future=True)
        with Session() as s:
            n_files = s.scalar(select(func.count()).select_from(File)) or 0
            keys = list(s.scalars(select(File.key)).all())
        return {"ok": True, "files": n_files, "keys": keys}

    return router

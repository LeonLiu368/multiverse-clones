"""Token-gated control plane for seeding/resetting a running workspace.

Operator/harness-only. Gated by ``$GWS_CONTROL_TOKEN`` (constant-time compare);
unset or mismatch → 404 so it isn't discoverable. The agent never gets the token.
No grading endpoint — verification stays on the public Drive/Docs surface.
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
    expected = os.environ.get("GWS_CONTROL_TOKEN")
    if not expected:
        return False
    return bool(provided) and hmac.compare_digest(provided, expected)


def make_control_router(engine: Engine) -> APIRouter:
    router = APIRouter()

    def guard(tok: str | None) -> None:
        if not _token_ok(tok):
            raise HTTPException(status_code=404)

    def reseed(seed: dict[str, Any]) -> dict[str, int]:
        Base.metadata.drop_all(engine)
        init_db(engine)
        return load_seed_into_engine(seed, engine)

    @router.post("/_control/seed")
    async def control_seed(request: Request, x_control_token: str | None = Header(None)) -> dict:
        guard(x_control_token)
        try:
            body = await request.json()
        except Exception:
            body = {}
        if body.get("seed") is None:
            raise HTTPException(status_code=400, detail="missing seed")
        return {"ok": True, "seeded": reseed(body["seed"])}

    @router.post("/_control/reset")
    def control_reset(x_control_token: str | None = Header(None)) -> dict:
        guard(x_control_token)
        Base.metadata.drop_all(engine)
        init_db(engine)
        return {"ok": True, "seeded": {"drive": 0, "documents": 0}}

    @router.get("/_control/status")
    def control_status(x_control_token: str | None = Header(None)) -> dict:
        from sqlalchemy import func, select
        from sqlalchemy.orm import sessionmaker

        from ..models import Document, DriveFile
        guard(x_control_token)
        S = sessionmaker(bind=engine, future=True)
        with S() as s:
            nf = s.scalar(select(func.count()).select_from(DriveFile)) or 0
            nd = s.scalar(select(func.count()).select_from(Document)) or 0
        return {"ok": True, "drive": nf, "documents": nd}

    return router

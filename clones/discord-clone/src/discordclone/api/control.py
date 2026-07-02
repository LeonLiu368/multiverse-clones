"""Token-gated control plane for seeding/resetting a *running* workspace.

OPERATOR/HARNESS surface, NOT an agent surface. It hydrates the live database
without restarting the container. Gated by a shared secret:

  * If ``$DISCORD_CONTROL_TOKEN`` is unset, every ``/_control/*`` route returns 404
    (disabled — the default in normal task runs).
  * If set, requests must send a matching ``X-Control-Token`` header. A mismatch
    also returns 404 (not 401) so the endpoint isn't discoverable by probing.

The agent's container is never given ``DISCORD_CONTROL_TOKEN``, so even sharing a
network it cannot drive this surface. There is NO grading endpoint here —
verification stays on the public API surface.
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
    expected = os.environ.get("DISCORD_CONTROL_TOKEN")
    if not expected:
        return False  # feature disabled
    return bool(provided) and hmac.compare_digest(provided, expected)


def make_control_router(engine: Engine) -> APIRouter:
    router = APIRouter()

    def _guard(x_control_token: str | None) -> None:
        if not _token_ok(x_control_token):
            raise HTTPException(status_code=404)

    def _reseed(seed: dict[str, Any]) -> dict[str, int]:
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
        if body.get("guild"):
            from ..seed.generator import generate
            seed = generate(guild=str(body["guild"]), seed=int(body.get("seed", 0)))
        elif body.get("seed_doc") is not None:
            seed = body["seed_doc"]
        else:
            raise HTTPException(status_code=400, detail="missing guild or seed_doc")
        return {"ok": True, "seeded": _reseed(seed)}

    @router.post("/_control/reset")
    def control_reset(x_control_token: str | None = Header(None)) -> dict:
        _guard(x_control_token)
        Base.metadata.drop_all(engine)
        init_db(engine)
        return {"ok": True, "seeded": {"users": 0, "guilds": 0, "channels": 0, "messages": 0}}

    @router.get("/_control/status")
    def control_status(x_control_token: str | None = Header(None)) -> dict:
        from sqlalchemy import func, select
        from sqlalchemy.orm import sessionmaker

        from ..models import Guild, Message

        _guard(x_control_token)
        Session = sessionmaker(bind=engine, future=True)
        with Session() as s:
            n_g = s.scalar(select(func.count()).select_from(Guild)) or 0
            n_m = s.scalar(select(func.count()).select_from(Message)) or 0
        return {"ok": True, "guilds": n_g, "messages": n_m}

    return router

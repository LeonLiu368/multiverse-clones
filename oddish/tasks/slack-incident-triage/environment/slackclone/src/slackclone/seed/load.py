"""Load a canonical seed into a SQLite database (file path or live engine)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from ..db import get_engine, init_db, session_factory
from .. import store
from . import schema


def load_seed_into_engine(seed: dict[str, Any], engine: Engine) -> dict[str, int]:
    """Write a canonical seed into ``engine`` (which must already have tables).

    Shared by the offline file loader and the live control-plane reseed, so both
    paths use the exact same upsert order against the same source of truth.
    """
    seed = schema.normalize(seed)
    Session: sessionmaker = session_factory(engine)
    with Session() as s:
        w = seed["workspace"]
        store.upsert_workspace(s, w["id"], w["name"], w["domain"])
        for u in seed["users"]:
            store.upsert_user(s, u)
        for c in seed["channels"]:
            store.upsert_channel(s, c)
        s.flush()
        for m in seed["messages"]:
            store.upsert_message(s, m)
        s.commit()
    return {
        "users": len(seed["users"]),
        "channels": len(seed["channels"]),
        "messages": len(seed["messages"]),
    }


def load_seed(seed: dict[str, Any], db_path: str) -> dict[str, int]:
    """Write a canonical seed to ``db_path``; returns row counts."""
    engine = get_engine(db_path)
    init_db(engine)
    return load_seed_into_engine(seed, engine)

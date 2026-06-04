"""Load a canonical seed into a fresh SQLite database."""

from __future__ import annotations

from typing import Any

from ..db import get_engine, init_db, session_factory
from .. import store
from . import schema


def load_seed(seed: dict[str, Any], db_path: str) -> dict[str, int]:
    """Write a canonical seed to ``db_path``; returns row counts."""
    seed = schema.normalize(seed)
    engine = get_engine(db_path)
    init_db(engine)
    Session = session_factory(engine)
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

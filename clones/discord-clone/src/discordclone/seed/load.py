"""Load a canonical seed into a SQLite database (file path or live engine)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from .. import store
from ..db import get_engine, init_db, session_factory
from . import schema


def load_seed_into_engine(seed: dict[str, Any], engine: Engine) -> dict[str, int]:
    """Write a canonical seed into ``engine`` (tables must already exist).

    Shared by the offline loader and the live control-plane reseed, so both paths
    use the exact same insert order against the same source of truth (store.py).
    """
    seed = schema.normalize(seed)
    Session: sessionmaker = session_factory(engine)
    n_reactions = 0
    with Session() as s:
        for u in seed["users"]:
            store.upsert_user(s, u)
        for g in seed["guilds"]:
            store.upsert_guild(s, g)
        for c in seed["channels"]:
            store.upsert_channel(s, c)
        for m in seed["members"]:
            store.upsert_member(s, m["guild_id"], m)
        s.flush()
        for msg in seed["messages"]:
            store.insert_message(s, msg)
            for rx in msg.get("reactions", []):
                store.insert_reaction(s, msg["id"], rx["emoji"], rx["user_id"])
                n_reactions += 1
        s.commit()
    return {
        "users": len(seed["users"]),
        "guilds": len(seed["guilds"]),
        "channels": len(seed["channels"]),
        "members": len(seed["members"]),
        "messages": len(seed["messages"]),
        "reactions": n_reactions,
    }


def load_seed(seed: dict[str, Any], db_path: str) -> dict[str, int]:
    """Write a canonical seed to ``db_path``; returns row counts."""
    engine = get_engine(db_path)
    init_db(engine)
    return load_seed_into_engine(seed, engine)

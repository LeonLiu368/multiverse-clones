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
    n_blocks = 0
    n_comments = 0
    with Session() as s:
        for u in seed["users"]:
            store.upsert_user(s, u)
        for d in seed["databases"]:
            store.upsert_database(s, d)
        s.flush()
        for p in seed["pages"]:
            store.upsert_page(s, p)
            s.flush()
            for i, blk in enumerate(p.get("blocks", [])):
                blk = dict(blk)
                blk.setdefault("id", store.gen_uuid())
                blk.setdefault("created_time", p["created_time"])
                blk.setdefault("created_by", p["created_by"])
                blk["parent"] = {"type": "page_id", "page_id": p["id"]}
                blk["parent_id"] = p["id"]
                store.upsert_block(s, blk, i)
                n_blocks += 1
            for i, c in enumerate(p.get("comments", [])):
                c = dict(c)
                c.setdefault("id", store.gen_uuid())
                c.setdefault("created_time", p["created_time"])
                c["parent"] = {"type": "page_id", "page_id": p["id"]}
                c["page_id"] = p["id"]
                store.upsert_comment(s, c, i)
                n_comments += 1
        s.commit()
    return {
        "users": len(seed["users"]),
        "databases": len(seed["databases"]),
        "pages": len(seed["pages"]),
        "blocks": n_blocks,
        "comments": n_comments,
    }


def load_seed(seed: dict[str, Any], db_path: str) -> dict[str, int]:
    """Write a canonical seed to ``db_path``; returns row counts."""
    engine = get_engine(db_path)
    init_db(engine)
    return load_seed_into_engine(seed, engine)

"""Load a canonical seed into a SQLite database (file path or live engine)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from .. import store
from ..db import get_engine, init_db, session_factory
from . import schema


def load_seed_into_engine(seed: dict[str, Any], engine: Engine) -> dict[str, int]:
    seed = schema.normalize(seed)
    Session: sessionmaker = session_factory(engine)
    with Session() as s:
        for f in seed["drive"]:
            store.upsert_file(s, f)
        for d in seed["documents"]:
            store.upsert_document(s, d)
        for e in seed.get("calendar", []):
            store.upsert_event(s, e)
        for m in seed.get("gmail", []):
            store.upsert_message(s, m)
        s.commit()
    return {"drive": len(seed["drive"]), "documents": len(seed["documents"]),
            "calendar": len(seed.get("calendar", [])), "gmail": len(seed.get("gmail", []))}


def load_seed(seed: dict[str, Any], db_path: str) -> dict[str, int]:
    engine = get_engine(db_path)
    init_db(engine)
    return load_seed_into_engine(seed, engine)

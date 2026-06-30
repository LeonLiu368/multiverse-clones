"""Load a canonical seed into a SQLite database (file path or live engine)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from .. import store
from ..db import get_engine, init_db, session_factory
from . import schema


def load_seed_into_engine(seed: dict[str, Any], engine: Engine) -> dict[str, int]:
    """Write a canonical seed into ``engine`` (which must already have tables).

    Shared by the offline file loader and the live control-plane reseed, so both
    paths use the exact same upsert order against the same source of truth.
    """
    seed = schema.normalize(seed)
    Session: sessionmaker = session_factory(engine)
    # map each file to the project that lists it, so files land in the right project
    file_to_project: dict[str, str] = {}
    for p in seed["projects"]:
        for fk in p.get("files", []):
            file_to_project[fk] = p["id"]
    with Session() as s:
        t = seed["team"]
        store.upsert_team(s, t["id"], t.get("name", "team"))
        for p in seed["projects"]:
            store.upsert_project(s, p, t["id"])
        s.flush()
        for f in seed["files"]:
            store.upsert_file(s, f, project_id=file_to_project.get(f["key"], ""))
        s.commit()
    n_comments = sum(len(f.get("comments", [])) for f in seed["files"])
    n_versions = sum(len(f.get("versions", [])) for f in seed["files"])
    return {
        "projects": len(seed["projects"]),
        "files": len(seed["files"]),
        "comments": n_comments,
        "versions": n_versions,
    }


def load_seed(seed: dict[str, Any], db_path: str) -> dict[str, int]:
    """Write a canonical seed to ``db_path``; returns row counts."""
    engine = get_engine(db_path)
    init_db(engine)
    return load_seed_into_engine(seed, engine)
